#!/usr/bin/env python3
"""Post-send digest for 2026-06-01 manual prospect outreach + Cyber BCC extra (read-only reports)."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.campaigns.manual_outreach_2026_06_01 import (
    ACTIVE_CASE_ROWS,
    AUTO_REPLY_EXPECTED,
    CYBER_BCC_BOUNCED_EXPECTED,
    CYBER_BCC_RECIPIENTS,
    CYBER_BCC_SUBJECT,
    CYBER_BCC_TO,
    MANUAL_PROSPECT_ROWS,
    REPORT_PREFIX,
)
from origenlab_email_pipeline.campaigns.manual_outreach_failure_types import classify_failure_type
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_email_suppression import fetch_contact_email_suppression_row
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.email_business_filters import classify_email
from origenlab_email_pipeline.ndr_bounce_extraction import extract_failed_recipients_from_ndr
from origenlab_email_pipeline.outreach_contact_state import fetch_outreach_contact_state_row
from origenlab_email_pipeline.outreach_ingest_sync import (
    _batch_hits_from_ndr_dsn,
    _ndr_blob_from_row,
    cutoff_date_str,
    scan_batch_against_ingested_bounces_from_text,
)

_AUTO_ACK_FRAGMENTS = (
    "gracias por contactarnos",
    "caso finalizado",
    "soporte responderá",
    "soporte respondera",
    "72 horas",
)


def _read_exclusion_emails(path: Path, col: str = "email") -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            em = (row.get(col) or row.get("normalized_email") or "").strip().lower()
            if em and "@" in em:
                out.add(em)
    return out


def _scan_ndr_index(
    conn: sqlite3.Connection,
    *,
    since_days: int,
) -> dict[str, list[dict[str, str]]]:
    """email -> list of NDR evidence rows."""
    pred = sql_predicate_contacto_gmail_source()
    cutoff = cutoff_date_str(since_days=since_days)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        f"""
        SELECT sender, subject, recipients, full_body_clean, top_reply_clean, body,
               folder, date_iso, id
        FROM emails
        WHERE {pred}
          AND COALESCE(date_iso, '') >= ?
        ORDER BY date_iso DESC
        """,
        (cutoff,),
    )
    index: dict[str, list[dict[str, str]]] = {}
    for row in cur.fetchall():
        mapping = {k: row[k] for k in row.keys()}
        blob = _ndr_blob_from_row(mapping)
        tags = classify_email(
            sender=str(mapping.get("sender") or ""),
            subject=str(mapping.get("subject") or ""),
            body=blob,
        )
        if "bounce_ndr" not in (tags.get("tags") or []):
            continue
        for em in extract_failed_recipients_from_ndr(blob):
            index.setdefault(em, []).append(
                {
                    "date_iso": str(mapping.get("date_iso") or ""),
                    "subject": str(mapping.get("subject") or "")[:200],
                    "failure_type": classify_failure_type(blob),
                    "email_id": str(mapping.get("id") or ""),
                }
            )
    return index


def _scan_auto_replies(conn: sqlite3.Connection, *, since_days: int) -> list[dict[str, str]]:
    pred = sql_predicate_contacto_gmail_source()
    cutoff = cutoff_date_str(since_days=since_days)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        f"""
        SELECT sender, subject, full_body_clean, body_text_clean, body, date_iso, id
        FROM emails
        WHERE {pred}
          AND COALESCE(date_iso, '') >= ?
          AND COALESCE(sender, '') NOT LIKE '%@origenlab.cl%'
        ORDER BY date_iso DESC
        """,
        (cutoff,),
    )
    hits: list[dict[str, str]] = []
    for row in cur.fetchall():
        blob = " ".join(
            str(row[c] or "")
            for c in ("subject", "full_body_clean", "body_text_clean", "body")
        ).lower()
        if not any(f in blob for f in _AUTO_ACK_FRAGMENTS):
            continue
        sender = str(row["sender"] or "")
        from origenlab_email_pipeline.business_mart import emails_in

        found = emails_in(sender)
        em = found[0].lower() if found else sender.lower()
        if em in AUTO_REPLY_EXPECTED or "lacofar" in em or "idiem" in em:
            hits.append(
                {
                    "email": em,
                    "date_iso": str(row["date_iso"] or ""),
                    "subject": str(row["subject"] or "")[:200],
                    "snippet": blob[:240],
                }
            )
    return hits


def _csv_write(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_digest(
    conn: sqlite3.Connection,
    out_dir: Path,
    *,
    since_days: int = 3,
) -> dict[str, object]:
    out_dir = out_dir.resolve()
    ndr_index = _scan_ndr_index(conn, since_days=since_days)

    manual_all = [r.email.lower() for r in MANUAL_PROSPECT_ROWS]
    cyber_all = list(CYBER_BCC_RECIPIENTS)
    batch_text = "\n".join(manual_all + cyber_all)
    scan = scan_batch_against_ingested_bounces_from_text(
        conn,
        batch_text,
        since_days=since_days,
    )

    sent_rows: list[dict[str, object]] = []
    bounce_rows: list[dict[str, object]] = []
    delivered_rows: list[dict[str, object]] = []

    for row in MANUAL_PROSPECT_ROWS:
        em = row.email.lower()
        sup = fetch_contact_email_suppression_row(conn, email=em)
        ocs = fetch_outreach_contact_state_row(conn, em)
        ndr_hits = ndr_index.get(em, [])
        bounced = bool(ndr_hits) or em in scan.bad
        rec = {
            "email": em,
            "organization": row.organization,
            "subject": row.subject,
            "expected_status": row.expected_status,
            "suppressed": bool(sup),
            "suppression_code": str(sup.get("suppression_reason_code") or "") if sup else "",
            "outreach_state": str(ocs.get("state") or "") if ocs else "",
            "failure_type": (
                ndr_hits[0]["failure_type"]
                if ndr_hits
                else (row.expected_failure_type or "")
            ),
            "ndr_count": len(ndr_hits),
        }
        sent_rows.append(rec)
        if bounced:
            bounce_rows.append(rec)
        elif row.kind == "delivered_expected":
            delivered_rows.append(rec)

    cyber_sent: list[dict[str, object]] = []
    cyber_bounced: list[dict[str, object]] = []
    for em in cyber_all:
        el = em.lower()
        sup = fetch_contact_email_suppression_row(conn, email=el)
        ndr_hits = ndr_index.get(el, [])
        bounced = bool(ndr_hits) or el in scan.bad
        rec = {
            "email": el,
            "role": "cyber_bcc_extra",
            "to_primary": el == CYBER_BCC_TO.lower(),
            "subject": CYBER_BCC_SUBJECT,
            "suppressed": bool(sup),
            "failure_type": ndr_hits[0]["failure_type"] if ndr_hits else "",
            "expected_bounce": el in CYBER_BCC_BOUNCED_EXPECTED,
        }
        cyber_sent.append(rec)
        if bounced:
            cyber_bounced.append(rec)

    auto_replies = _scan_auto_replies(conn, since_days=since_days)

    domain_review: dict[str, list[str]] = {}
    for r in bounce_rows + cyber_bounced:
        dom = domain_of(str(r["email"]))
        if dom:
            domain_review.setdefault(dom, []).append(str(r["email"]))

    domain_rows = [
        {"domain": dom, "bounced_emails": ";".join(sorted(ems)), "count": len(ems)}
        for dom, ems in sorted(domain_review.items())
    ]

    contacted_path = out_dir / "contacted_exact_emails_for_exclusion.csv"
    bounced_path = out_dir / "bounced_emails_for_exclusion.csv"
    contacted_set = _read_exclusion_emails(contacted_path)
    bounced_set = _read_exclusion_emails(bounced_path)

    presend = out_dir / "presentacion_batch1_final_send_25.csv"
    presend_emails: set[str] = set()
    if presend.is_file():
        with presend.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = (row.get("email") or "").strip().lower()
                if em:
                    presend_emails.add(em)

    all_bounced = {str(r["email"]) for r in bounce_rows} | {str(r["email"]) for r in cyber_bounced}
    verification = {
        "manual_sent_count": len(MANUAL_PROSPECT_ROWS),
        "manual_bounced_count": len(bounce_rows),
        "manual_delivered_no_ndr_count": len(delivered_rows),
        "cyber_bcc_count": len(cyber_all),
        "cyber_bcc_bounced_count": len(cyber_bounced),
        "auto_replies_count": len(auto_replies),
        "all_manual_in_contacted_exclusion": all(
            r.email.lower() in contacted_set for r in MANUAL_PROSPECT_ROWS
        ),
        "all_bounced_suppressed": all(
            fetch_contact_email_suppression_row(conn, email=em) is not None for em in all_bounced
        ),
        "bounced_not_in_presend_batch1": not (all_bounced & presend_emails),
        "active_cases": [r.email for r in ACTIVE_CASE_ROWS],
    }

    prefix = REPORT_PREFIX
    _csv_write(
        out_dir / f"{prefix}_sent.csv",
        [
            "email",
            "organization",
            "subject",
            "expected_status",
            "suppressed",
            "suppression_code",
            "outreach_state",
            "failure_type",
            "ndr_count",
        ],
        sent_rows,
    )
    _csv_write(
        out_dir / f"{prefix}_bounces.csv",
        [
            "email",
            "organization",
            "subject",
            "expected_status",
            "suppressed",
            "suppression_code",
            "failure_type",
            "ndr_count",
        ],
        bounce_rows + cyber_bounced,
    )
    _csv_write(
        out_dir / f"{prefix}_delivered_no_ndr.csv",
        ["email", "organization", "subject", "outreach_state"],
        delivered_rows,
    )
    _csv_write(
        out_dir / f"{prefix}_auto_replies.csv",
        ["email", "date_iso", "subject", "snippet"],
        auto_replies,
    )
    _csv_write(
        out_dir / f"{prefix}_domain_review.csv",
        ["domain", "bounced_emails", "count"],
        domain_rows,
    )

    cyber_csv = out_dir / f"{prefix}_cyber_bcc.csv"
    _csv_write(
        cyber_csv,
        ["email", "role", "to_primary", "subject", "suppressed", "failure_type", "expected_bounce"],
        cyber_sent,
    )

    digest_md = out_dir / f"{prefix}_digest.md"
    status_md = out_dir / f"{prefix}_dashboard_status.md"
    summary = {
        "date": "2026-06-01",
        "verification": verification,
        "scan_bad_count": len(scan.bad),
        "scan_good_count": len(scan.good),
    }
    digest_md.write_text(
        _render_digest_md(summary, sent_rows, bounce_rows, cyber_bounced, auto_replies),
        encoding="utf-8",
    )
    status_md.write_text(
        _render_dashboard_status_md(verification, ACTIVE_CASE_ROWS),
        encoding="utf-8",
    )
    (out_dir / f"{prefix}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def _render_digest_md(
    summary: dict[str, object],
    sent: list[dict[str, object]],
    bounces: list[dict[str, object]],
    cyber_bounced: list[dict[str, object]],
    auto_replies: list[dict[str, str]],
) -> str:
    v = summary["verification"]
    lines = [
        "# Manual outreach digest — 2026-06-01",
        "",
        "## Verification",
        f"- Manual sends: {v['manual_sent_count']}",
        f"- Manual bounces (NDR): {v['manual_bounced_count']}",
        f"- Delivered (no NDR in window): {v['manual_delivered_no_ndr_count']}",
        f"- Cyber BCC recipients: {v['cyber_bcc_count']}",
        f"- Cyber BCC bounces: {v['cyber_bcc_bounced_count']}",
        f"- Auto-replies: {v['auto_replies_count']}",
        f"- All manual in contacted exclusion: {v['all_manual_in_contacted_exclusion']}",
        f"- All bounced exact-suppressed: {v['all_bounced_suppressed']}",
        f"- Bounced absent from presend batch1: {v['bounced_not_in_presend_batch1']}",
        "",
        "## Manual prospect bounces",
    ]
    for r in bounces:
        if r.get("role") == "cyber_bcc_extra":
            continue
        lines.append(f"- {r['email']}: {r.get('failure_type')} ({r.get('organization')})")
    lines.append("")
    lines.append("## Cyber BCC bounces")
    for r in cyber_bounced:
        lines.append(f"- {r['email']}: {r.get('failure_type')}")
    lines.append("")
    lines.append("## Auto-ack (not human opportunity)")
    for ar in auto_replies:
        lines.append(f"- {ar['email']}: {ar.get('subject', '')[:80]}")
    lines.append("")
    lines.append("## Delivered manual (no NDR)")
    bounced_emails = {str(x["email"]) for x in bounces}
    for r in sent:
        if int(r.get("ndr_count") or 0) == 0 and str(r["email"]) not in bounced_emails:
            lines.append(f"- {r['email']}")
    return "\n".join(lines) + "\n"


def _render_dashboard_status_md(verification: dict[str, object], active_cases) -> str:
    lines = [
        "# Dashboard status — manual outreach 2026-06-01",
        "",
        "Prospectos: manual sends → `contacted` / exclusion CSVs; bounces → exact suppression.",
        "Bandeja: CESMEC + Hielscher remain real action cases (not marketing prospect).",
        "Cyber BCC extra → `campaign_outreach`, hidden from default warm queue.",
        "",
        "## Checks",
    ]
    for k, val in verification.items():
        lines.append(f"- {k}: {val}")
    lines.append("")
    lines.append("## Active cases (do not treat as generic prospect campaign)")
    for row in active_cases:
        lines.append(f"- {row.email}: {row.expected_status} — {row.organization}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
    )
    ap.add_argument("--since-days", type=int, default=3)
    args = ap.parse_args(argv)

    db_path = args.db or load_settings().resolved_sqlite_path()
    conn = connect(db_path)
    try:
        summary = build_digest(conn, args.out_dir, since_days=args.since_days)
    finally:
        conn.close()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
