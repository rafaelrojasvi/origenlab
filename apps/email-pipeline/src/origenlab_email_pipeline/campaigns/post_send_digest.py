"""Post-send ingest digest from Gmail SQLite (read-only reports, no sends)."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.campaigns.manual_outreach_failure_types import classify_failure_type
from origenlab_email_pipeline.contact_email_suppression import fetch_contact_email_suppression_row
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.email_business_filters import classify_email
from origenlab_email_pipeline.ndr_bounce_extraction import extract_failed_recipients_from_ndr
from origenlab_email_pipeline.outreach_contact_state import fetch_outreach_contact_state_row
from origenlab_email_pipeline.outreach_ingest_sync import _ndr_blob_from_row, cutoff_date_str

REPORT_DATE = "2026-06-01"
FILE_STEM = "post_send"

# Subjects for manual / mom outreach in this window (partial match).
_OUTREACH_SUBJECT_FRAGMENTS = (
    "seguimiento",
    "equipos para laboratorio",
    "presentación origenlab",
    "cyber",
    "origenlab",
)

_AUTO_ACK_FRAGMENTS = (
    "gracias por contactarnos",
    "caso finalizado",
    "soporte responderá",
    "soporte respondera",
    "72 horas",
    "fuera de la oficina",
    "out of office",
    "automatic reply",
    "respuesta automática",
)


@dataclass(frozen=True)
class SentRecipientRow:
    email: str
    domain: str
    subject: str
    date_iso: str
    email_id: str
    sent_folder: str


def _csv_write(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _read_exclusion_emails(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            em = (row.get("normalized_email") or row.get("email") or "").strip().lower()
            if em and "@" in em:
                out.add(em)
    return out


def scan_sent_recipients(
    conn: sqlite3.Connection,
    *,
    since_days: int,
    sent_folders: tuple[str, ...],
    gmail_user: str,
) -> tuple[list[SentRecipientRow], dict[str, int]]:
    """Parse Sent-folder rows in the ingest window; return per-recipient rows + ingest stats."""
    pred = sql_predicate_contacto_gmail_source()
    cutoff = cutoff_date_str(since_days=since_days)
    like_pat = f"gmail:{gmail_user.strip().lower()}/%"
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not folders:
        return [], {"sent_rows": 0, "sent_messages": 0}
    ph = ",".join("?" * len(folders))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        f"""
        SELECT id, subject, recipients, date_iso, folder
        FROM emails
        WHERE {pred}
          AND lower(source_file) LIKE ?
          AND folder IN ({ph})
          AND COALESCE(date_iso, '') >= ?
        ORDER BY date_iso DESC
        """,
        (like_pat, *folders, cutoff),
    )
    stats = {"sent_messages": 0, "sent_rows": 0}
    out: list[SentRecipientRow] = []
    seen_msg: set[int] = set()
    for row in cur.fetchall():
        stats["sent_messages"] += 1
        eid = str(row["id"] or "")
        if eid:
            seen_msg.add(int(eid) if str(eid).isdigit() else hash(eid))
        subj = str(row["subject"] or "")
        subj_l = subj.lower()
        if not any(frag in subj_l for frag in _OUTREACH_SUBJECT_FRAGMENTS):
            continue
        for em in emails_in(str(row["recipients"] or "")):
            if em.endswith("@origenlab.cl") or em.endswith("@labdelivery.cl"):
                continue
            stats["sent_rows"] += 1
            out.append(
                SentRecipientRow(
                    email=em,
                    domain=domain_of(em) or "",
                    subject=subj[:300],
                    date_iso=str(row["date_iso"] or ""),
                    email_id=eid,
                    sent_folder=str(row["folder"] or ""),
                )
            )
    stats["sent_messages_unique"] = len(seen_msg)
    return out, stats


def scan_ndr_index(
    conn: sqlite3.Connection,
    *,
    since_days: int,
) -> dict[str, list[dict[str, str]]]:
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
        subj_l = str(mapping.get("subject") or "").lower()
        if "notification (delay)" in subj_l or subj_l.strip().endswith("(delay)"):
            continue
        for em in extract_failed_recipients_from_ndr(blob):
            index.setdefault(em, []).append(
                {
                    "date_iso": str(mapping.get("date_iso") or ""),
                    "subject": str(mapping.get("subject") or "")[:200],
                    "failure_type": classify_failure_type(blob),
                    "email_id": str(mapping.get("id") or ""),
                    "ndr_snippet": blob[:240].replace("\n", " "),
                }
            )
    return index


def scan_auto_replies(conn: sqlite3.Connection, *, since_days: int) -> list[dict[str, str]]:
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
            str(row[c] or "") for c in ("subject", "full_body_clean", "body_text_clean", "body")
        ).lower()
        tags = classify_email(
            sender=str(row["sender"] or ""),
            subject=str(row["subject"] or ""),
            body=blob,
        )
        tag_set = set(tags.get("tags") or [])
        is_auto = any(f in blob for f in _AUTO_ACK_FRAGMENTS) or "auto_reply" in tag_set
        if not is_auto:
            continue
        found = emails_in(str(row["sender"] or ""))
        em = found[0].lower() if found else str(row["sender"] or "").lower()
        hits.append(
            {
                "email": em,
                "date_iso": str(row["date_iso"] or ""),
                "subject": str(row["subject"] or "")[:200],
                "snippet": blob[:240],
                "classification": "auto_reply",
            }
        )
    return hits


def scan_human_replies(
    conn: sqlite3.Connection,
    *,
    since_days: int,
    sent_emails: set[str],
) -> list[dict[str, str]]:
    """INBOX replies from sent recipients that are not NDR/auto-ack."""
    pred = sql_predicate_contacto_gmail_source()
    cutoff = cutoff_date_str(since_days=since_days)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        f"""
        SELECT sender, subject, date_iso, id, folder
        FROM emails
        WHERE {pred}
          AND COALESCE(date_iso, '') >= ?
          AND COALESCE(folder, '') NOT LIKE '%Enviados%'
          AND COALESCE(folder, '') NOT LIKE '%Sent%'
        ORDER BY date_iso DESC
        """,
        (cutoff,),
    )
    hits: list[dict[str, str]] = []
    for row in cur.fetchall():
        found = emails_in(str(row["sender"] or ""))
        em = found[0].lower() if found else ""
        if not em or em not in sent_emails:
            continue
        blob = str(row["subject"] or "").lower()
        if any(f in blob for f in _AUTO_ACK_FRAGMENTS):
            continue
        hits.append(
            {
                "email": em,
                "date_iso": str(row["date_iso"] or ""),
                "subject": str(row["subject"] or "")[:200],
                "classification": "human_reply_candidate",
            }
        )
    return hits


def build_post_send_digest(
    conn: sqlite3.Connection,
    out_dir: Path,
    *,
    since_days: int,
    sent_folders: tuple[str, ...],
    gmail_user: str,
    ingest_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    sent_list, sent_stats = scan_sent_recipients(
        conn, since_days=since_days, sent_folders=sent_folders, gmail_user=gmail_user
    )
    ndr_index = scan_ndr_index(conn, since_days=since_days)
    auto_replies = scan_auto_replies(conn, since_days=since_days)

    sent_by_email: dict[str, SentRecipientRow] = {}
    for row in sent_list:
        prev = sent_by_email.get(row.email)
        if prev is None or row.date_iso > prev.date_iso:
            sent_by_email[row.email] = row

    bounce_rows: list[dict[str, Any]] = []
    delivered_rows: list[dict[str, Any]] = []
    new_sent_rows: list[dict[str, Any]] = []

    for em, srow in sorted(sent_by_email.items()):
        ndr_hits = ndr_index.get(em, [])
        sup = fetch_contact_email_suppression_row(conn, email=em)
        ocs = fetch_outreach_contact_state_row(conn, em)
        bounced = bool(ndr_hits)
        rec: dict[str, Any] = {
            "email": em,
            "domain": srow.domain,
            "subject": srow.subject,
            "date_iso": srow.date_iso,
            "sent_email_id": srow.email_id,
            "suppressed": bool(sup),
            "suppression_code": str(sup.get("suppression_reason_code") or "") if sup else "",
            "outreach_state": str(ocs.get("state") or "") if ocs else "",
            "failure_type": ndr_hits[0]["failure_type"] if ndr_hits else "",
            "ndr_count": len(ndr_hits),
            "ndr_email_id": ndr_hits[0]["email_id"] if ndr_hits else "",
        }
        new_sent_rows.append(rec)
        if bounced:
            rec["safety_reason"] = "ndr_bounce_dsn"
            bounce_rows.append(rec)
        else:
            delivered_rows.append(rec)

    # Bounces in window not matched to a tracked sent row (still suppress via NDR scan).
    orphan_bounces: list[dict[str, Any]] = []
    for em, hits in sorted(ndr_index.items()):
        if em in sent_by_email:
            continue
        sup = fetch_contact_email_suppression_row(conn, email=em)
        orphan_bounces.append(
            {
                "email": em,
                "domain": domain_of(em) or "",
                "failure_type": hits[0]["failure_type"],
                "ndr_count": len(hits),
                "suppressed": bool(sup),
                "note": "bounce_in_window_not_in_outreach_subject_sent_filter",
            }
        )
        bounce_rows.append(
            {
                "email": em,
                "domain": domain_of(em) or "",
                "subject": hits[0].get("subject", ""),
                "failure_type": hits[0]["failure_type"],
                "ndr_count": len(hits),
                "suppressed": bool(sup),
                "orphan_bounce": True,
            }
        )

    domain_review: dict[str, list[str]] = defaultdict(list)
    for r in bounce_rows:
        dom = str(r.get("domain") or "")
        if dom:
            domain_review[dom].append(str(r["email"]))
    domain_rows = [
        {
            "domain": dom,
            "bounced_emails": ";".join(sorted(set(ems))),
            "count": len(set(ems)),
            "domain_suppression_candidate": "review_only",
        }
        for dom, ems in sorted(domain_review.items())
    ]

    contacted_path = out_dir / "contacted_exact_emails_for_exclusion.csv"
    bounced_path = out_dir / "bounced_emails_for_exclusion.csv"
    contacted_set = _read_exclusion_emails(contacted_path)
    bounced_set = _read_exclusion_emails(bounced_path)

    human_replies = scan_human_replies(
        conn, since_days=since_days, sent_emails=set(sent_by_email)
    )

    known_evidence = {
        "atencionclienteschile@mxns.com",
        "loreto.castro@bayer.com",
        "adquisiciones@medcell.cl",
        "farmacia@heel.cl",
        "pquijada@sanitas.cl",
        "mauricio.aceiton@unilever.com",
        "tecnofar@tecnofarma.cl",
        "snunez@valma.cl",
        "pharmainvesti@pharmainvesti.cl",
        "informacion_productos@bestpharma.cl",
    }
    evidence_check = {
        em: {
            "in_sent_digest": em in sent_by_email,
            "in_bounce_digest": em in {str(r["email"]) for r in bounce_rows},
            "suppressed": fetch_contact_email_suppression_row(conn, email=em) is not None,
        }
        for em in sorted(known_evidence)
    }

    false_positive_notes: list[str] = []
    for r in bounce_rows:
        em = str(r["email"])
        hits = ndr_index.get(em, [])
        if not hits:
            false_positive_notes.append(f"{em}: marked bounce without NDR index")
        if em in sent_by_email and not hits:
            false_positive_notes.append(f"{em}: sent outreach but no DSN in window")

    d = REPORT_DATE
    paths = {
        "digest": out_dir / f"{FILE_STEM}_digest_{d}.md",
        "new_sent": out_dir / f"{FILE_STEM}_new_sent_{d}.csv",
        "bounces": out_dir / f"{FILE_STEM}_bounces_{d}.csv",
        "delivered": out_dir / f"{FILE_STEM}_delivered_no_ndr_{d}.csv",
        "auto_replies": out_dir / f"{FILE_STEM}_auto_replies_{d}.csv",
        "domain_review": out_dir / f"{FILE_STEM}_domain_review_{d}.csv",
        "summary": out_dir / f"{FILE_STEM}_safety_summary_{d}.json",
    }

    _csv_write(
        paths["new_sent"],
        [
            "email",
            "domain",
            "subject",
            "date_iso",
            "suppressed",
            "suppression_code",
            "outreach_state",
            "failure_type",
            "ndr_count",
        ],
        new_sent_rows,
    )
    _csv_write(
        paths["bounces"],
        [
            "email",
            "domain",
            "subject",
            "failure_type",
            "ndr_count",
            "suppressed",
            "orphan_bounce",
        ],
        bounce_rows,
    )
    _csv_write(
        paths["delivered"],
        ["email", "domain", "subject", "date_iso", "outreach_state"],
        delivered_rows,
    )
    _csv_write(
        paths["auto_replies"],
        ["email", "date_iso", "subject", "snippet", "classification"],
        auto_replies,
    )
    _csv_write(
        paths["domain_review"],
        ["domain", "bounced_emails", "count", "domain_suppression_candidate"],
        domain_rows,
    )

    summary: dict[str, Any] = {
        "date": REPORT_DATE,
        "since_days": since_days,
        "ingest": ingest_stats or {},
        "sent_stats": sent_stats,
        "unique_sent_recipients": len(sent_by_email),
        "total_bounces_in_window": len(ndr_index),
        "bounce_rows_reported": len(bounce_rows),
        "orphan_bounces": len(orphan_bounces),
        "delivered_no_ndr": len(delivered_rows),
        "auto_replies": len(auto_replies),
        "human_reply_candidates": len(human_replies),
        "contacted_exact_count": len(contacted_set),
        "bounced_exclusion_count": len(bounced_set),
        "evidence_check": evidence_check,
        "false_positive_notes": false_positive_notes,
    }
    paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    paths["digest"].write_text(
        _render_digest_md(summary, new_sent_rows, bounce_rows, delivered_rows, auto_replies),
        encoding="utf-8",
    )
    summary["paths"] = {k: str(v) for k, v in paths.items()}
    return summary


def _render_digest_md(
    summary: dict[str, Any],
    sent: list[dict[str, Any]],
    bounces: list[dict[str, Any]],
    delivered: list[dict[str, Any]],
    auto_replies: list[dict[str, str]],
) -> str:
    lines = [
        f"# Post-send digest — {summary.get('date')}",
        "",
        "## Ingest",
        f"- Gmail ingest stats: `{json.dumps(summary.get('ingest', {}), ensure_ascii=False)}`",
        f"- Sent stats (outreach subjects): `{json.dumps(summary.get('sent_stats', {}), ensure_ascii=False)}`",
        "",
        "## Counts",
        f"- Unique sent recipients (filtered subjects): **{summary.get('unique_sent_recipients')}**",
        f"- Distinct NDR bounces in window: **{summary.get('total_bounces_in_window')}**",
        f"- Bounce rows in report: **{summary.get('bounce_rows_reported')}**",
        f"- Orphan bounces (not in sent filter): **{summary.get('orphan_bounces')}**",
        f"- Delivered / no NDR: **{summary.get('delivered_no_ndr')}**",
        f"- Auto-replies: **{summary.get('auto_replies')}**",
        f"- contacted_exact CSV rows: **{summary.get('contacted_exact_count')}**",
        f"- bounced exclusion CSV rows: **{summary.get('bounced_exclusion_count')}**",
        "",
        "## Evidence check (operator list)",
    ]
    for em, chk in (summary.get("evidence_check") or {}).items():
        lines.append(f"- `{em}`: {chk}")
    lines.extend(["", "## Bounces", ""])
    for r in bounces[:80]:
        flag = " (orphan)" if r.get("orphan_bounce") else ""
        lines.append(
            f"- {r['email']}: {r.get('failure_type')} — suppressed={r.get('suppressed')}{flag}"
        )
    if len(bounces) > 80:
        lines.append(f"- … and {len(bounces) - 80} more (see CSV)")
    lines.extend(["", "## Delivered (no NDR in window)", ""])
    for r in delivered[:40]:
        lines.append(f"- {r['email']}: {r.get('subject', '')[:60]}")
    lines.extend(["", "## Auto-replies (not human opportunity)", ""])
    for ar in auto_replies[:20]:
        lines.append(f"- {ar['email']}: {ar.get('subject', '')[:80]}")
    fps = summary.get("false_positive_notes") or []
    if fps:
        lines.extend(["", "## Suspicious attributions", ""])
        for note in fps:
            lines.append(f"- {note}")
    lines.append("")
    lines.append("> Read-only digest. Exact-email suppressions only; domain blocks are review-only.")
    return "\n".join(lines) + "\n"
