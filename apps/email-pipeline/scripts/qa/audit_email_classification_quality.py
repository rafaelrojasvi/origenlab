#!/usr/bin/env python3
"""Read-only QA: heuristic «commercial type» labels on canonical Gmail (contacto@origenlab.cl).

Does **not** mutate SQLite, suppression, or outreach state. Uses keyword/heuristic rules from
:mod:`origenlab_email_pipeline.email_classification_qa` — not a claim of ground truth.

Examples:
  uv run python scripts/qa/audit_email_classification_quality.py --days 90 --limit 400
  uv run python scripts/qa/audit_email_classification_quality.py --json --out /tmp/classification_audit.json

Internal domains for counterparty parsing default to ``origenlab.cl`` and ``labdelivery.cl`` only
(see ``qa_operational_internal_domains``). Optional comma-separated env:
``ORIGENLAB_INTERNAL_DOMAINS=partner.cl``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import (
    domain_of,
    emails_in,
    primary_sender_email,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.email_classification_qa import (
    canonical_where_for_alias,
    classify_email_row,
    external_contact_emails,
    mark_no_response_candidates,
    qa_operational_internal_domains,
    recommended_action_for_classification,
    spanish_heuristic_bucket_label,
)
from origenlab_email_pipeline.marketing_supplier_domains import supplier_email_domains

# Snapshot before heuristic hardening (canonical Gmail, days=120, limit=2500, ~2026-05-14).
_AUDIT_HEURISTIC_BASELINE_V1: dict[str, object] = {
    "label": "pre-hardening snapshot (operator run)",
    "rows_scanned": 1054,
    "counts_by_primary": {
        "quote_request_inbound": 51,
        "university_or_research": 98,
        "cotizacion_sent": 172,
        "unclassified": 599,
        "needs_follow_up": 31,
        "supplier_or_vendor": 36,
        "bad_email_or_bounce": 65,
        "client_or_buyer": 2,
        "no_response_after_sent": 52,
    },
    "ambiguous_rows": 119,
    "likely_missed_quote_request": 49,
    "internal_domains_used": [
        "dhl.com",
        "facebookmail.com",
        "labdelivery.cl",
        "labx.com",
        "mercadopublico.cl",
        "origenlab.cl",
        "soviquim.cl",
        "twitter.com",
        "wherex.com",
    ],
}


def _emit_baseline_delta(summary: dict[str, object], *, file=sys.stderr) -> None:
    """Print stderr comparison vs fixed baseline (informational)."""
    b = _AUDIT_HEURISTIC_BASELINE_V1
    print("", file=file)
    print("=== QA heuristic delta vs baseline (v1 snapshot) ===", file=file)
    print(f"Baseline: {b.get('label')}", file=file)
    cur_counts = summary.get("counts_by_primary") or {}
    base_counts = b.get("counts_by_primary") or {}
    keys = sorted(set(cur_counts) | set(base_counts))
    for k in keys:
        a = int(base_counts.get(k, 0) or 0)
        c = int(cur_counts.get(k, 0) or 0)
        if a != c or k in ("unclassified", "quote_request_inbound"):
            print(f"  counts[{k}]: {a} -> {c}", file=file)
    print(
        f"  ambiguous_rows: {int(b.get('ambiguous_rows', 0))} -> {int(summary.get('ambiguous_rows', 0))}",
        file=file,
    )
    print(
        "  likely_missed_quote_request: "
        f"{int(b.get('likely_missed_quote_request', 0))} -> {int(summary.get('likely_missed_quote_request', 0))}",
        file=file,
    )
    print(
        "  internal_domains (baseline was polluted): "
        f"{len(b.get('internal_domains_used', []))} domains -> {summary.get('internal_domains_used')}",
        file=file,
    )
    print("=== end delta ===", file=file)


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True, timeout=120.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _fetch_sample_rows(
    conn: sqlite3.Connection,
    *,
    predicate_on_e: str,
    days: int,
    limit: int,
) -> list[sqlite3.Row]:
    d = max(1, min(int(days), 3660))
    lim = max(10, min(int(limit), 50_000))
    day_param = f"-{d} days"
    if _table_exists(conn, "document_master"):
        doc_sel = (
            "(SELECT group_concat(DISTINCT d.doc_type) "
            "FROM document_master d WHERE d.email_id = e.id) AS doc_types"
        )
    else:
        doc_sel = "NULL AS doc_types"
    sql = f"""
        SELECT
          e.id,
          e.date_iso,
          e.folder,
          e.sender,
          e.recipients,
          e.subject,
          COALESCE(e.body, '') AS body,
          COALESCE(e.full_body_clean, '') AS full_body_clean,
          COALESCE(e.top_reply_clean, '') AS top_reply_clean,
          {doc_sel}
        FROM emails e
        WHERE ({predicate_on_e})
          AND e.date_iso IS NOT NULL AND trim(e.date_iso) != ''
          AND date(e.date_iso) >= date('now', ?)
        ORDER BY e.date_iso DESC
        LIMIT ?
    """
    cur = conn.execute(sql, (day_param, lim))
    return cur.fetchall()


def _batch_mart_strings(
    conn: sqlite3.Connection,
    rows: Sequence[sqlite3.Row],
    *,
    internal: frozenset[str],
) -> tuple[dict[int, str], dict[str, str], dict[str, str]]:
    """Return (signals_by_email_id, contact_org_type_by_email, org_type_by_domain)."""
    ids = [int(r["id"]) for r in rows]
    signals_by_id: dict[int, str] = {}
    if ids and _table_exists(conn, "opportunity_signals"):
        step = 400
        for off in range(0, len(ids), step):
            chunk = ids[off : off + step]
            qm = ",".join("?" * len(chunk))
            cur = conn.execute(
                f"""
                SELECT eid, group_concat(signal_type, '|') AS s
                FROM (
                    SELECT DISTINCT email_id AS eid, signal_type
                    FROM opportunity_signals
                    WHERE email_id IN ({qm})
                ) AS sig_dedup
                GROUP BY eid
                """,
                chunk,
            )
            for row in cur.fetchall():
                signals_by_id[int(row["eid"])] = str(row["s"] or "")

    emails_l: set[str] = set()
    domains_l: set[str] = set()
    for r in rows:
        pe = (primary_sender_email(r["sender"] or "") or "").strip().lower()
        if pe:
            emails_l.add(pe)
        for e in emails_in(r["recipients"] or ""):
            emails_l.add(e.lower().strip())
        ext = external_contact_emails(r["sender"], r["recipients"], internal_domains_lower=internal)
        for e in ext:
            dom = domain_of(e)
            if dom:
                domains_l.add(dom.lower().strip())

    contact_by_email: dict[str, str] = {}
    if emails_l and _table_exists(conn, "contact_master"):
        em_list = sorted(emails_l)
        step = 400
        for off in range(0, len(em_list), step):
            chunk = em_list[off : off + step]
            qm = ",".join("?" * len(chunk))
            cur = conn.execute(
                f"""
                SELECT lower(trim(email)) AS em,
                       trim(COALESCE(organization_type_guess,'')) AS ot,
                       COALESCE(quote_email_count,0) AS qc
                FROM contact_master
                WHERE lower(trim(email)) IN ({qm})
                """,
                chunk,
            )
            for row in cur.fetchall():
                em = str(row["em"] or "")
                ot = str(row["ot"] or "")
                qc = int(row["qc"] or 0)
                contact_by_email[em] = f"type={ot or '?'}" + (f";quote_emails={qc}" if qc else "")

    org_by_domain: dict[str, str] = {}
    if domains_l and _table_exists(conn, "organization_master"):
        dom_list = sorted(domains_l)
        step = 400
        for off in range(0, len(dom_list), step):
            chunk = dom_list[off : off + step]
            qm = ",".join("?" * len(chunk))
            cur = conn.execute(
                f"""
                SELECT lower(trim(domain)) AS dom,
                       trim(COALESCE(organization_type_guess,'')) AS ot
                FROM organization_master
                WHERE lower(trim(domain)) IN ({qm})
                """,
                chunk,
            )
            for row in cur.fetchall():
                org_by_domain[str(row["dom"] or "")] = str(row["ot"] or "")

    return signals_by_id, contact_by_email, org_by_domain


def _mart_hint_line(
    r: sqlite3.Row,
    *,
    internal: frozenset[str],
    signals_by_id: dict[int, str],
    contact_by_email: dict[str, str],
    org_by_domain: dict[str, str],
) -> str:
    parts: list[str] = []
    sid = int(r["id"])
    if sid in signals_by_id and signals_by_id[sid]:
        parts.append("signals=" + signals_by_id[sid])
    pe = (primary_sender_email(r["sender"] or "") or "").strip().lower()
    if pe and pe in contact_by_email:
        parts.append("contact_master:" + contact_by_email[pe])
    ext = sorted(external_contact_emails(r["sender"], r["recipients"], internal_domains_lower=internal))
    for e in ext:
        d = domain_of(e)
        if d and d.lower() in org_by_domain and org_by_domain[d.lower()]:
            parts.append("organization_master:" + org_by_domain[d.lower()])
            break
    return " | ".join(parts)


def _snippet(text: str | None, n: int = 140) -> str:
    if not text:
        return ""
    s = " ".join(str(text).split())
    return (s[:n] + "…") if len(s) > n else s


def run_audit(
    conn: sqlite3.Connection,
    *,
    days: int,
    limit: int,
    legacy_also: bool,
) -> dict[str, Any]:
    supplier_domains = supplier_email_domains(conn)
    internal = qa_operational_internal_domains()

    pred_canon = canonical_where_for_alias("e")
    rows = _fetch_sample_rows(conn, predicate_on_e=pred_canon, days=days, limit=limit)
    signals_by_id, contact_by_email, org_by_domain = _batch_mart_strings(conn, rows, internal=internal)

    by_primary: Counter[str] = Counter()
    ambiguous_n = 0
    likely_missed_n = 0
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    review_rows: list[dict[str, str]] = []

    for r in rows:
        doc_types = r["doc_types"]
        rc = classify_email_row(
            folder=r["folder"],
            subject=r["subject"],
            sender=r["sender"],
            recipients=r["recipients"],
            body=r["body"],
            full_body_clean=r["full_body_clean"],
            top_reply_clean=r["top_reply_clean"],
            doc_types_csv=doc_types,
            supplier_domains=supplier_domains,
            internal_domains_lower=internal,
        )
        by_primary[rc.primary] += 1
        if rc.ambiguous:
            ambiguous_n += 1
        if rc.likely_missed:
            likely_missed_n += 1

        mart_hint = _mart_hint_line(
            r,
            internal=internal,
            signals_by_id=signals_by_id,
            contact_by_email=contact_by_email,
            org_by_domain=org_by_domain,
        )
        ev_snip = " | ".join(rc.evidence[:4])
        if mart_hint:
            ev_snip = (ev_snip + " | " if ev_snip else "") + mart_hint

        ex = {
            "id": int(r["id"]),
            "date_iso": r["date_iso"],
            "folder": r["folder"],
            "from_addr": _snippet(r["sender"], 120),
            "to_addrs": _snippet(r["recipients"], 120),
            "subject": _snippet(r["subject"], 160),
            "detected_category": rc.primary,
            "all_categories": ",".join(rc.categories),
            "confidence": rc.confidence,
            "evidence_snippet": _snippet(ev_snip, 400),
            "ambiguous": rc.ambiguous,
            "recommended_action": rc.recommended_action,
            "likely_missed_classification": rc.likely_missed,
            "mart_context": mart_hint,
        }
        if len(examples[rc.primary]) < 15:
            examples[rc.primary].append(ex)

        review_rows.append(
            {
                "email_id": str(r["id"]),
                "date_iso": str(r["date_iso"] or ""),
                "folder": str(r["folder"] or ""),
                "from_addr": str(r["sender"] or ""),
                "to_addrs": str(r["recipients"] or ""),
                "subject": str(r["subject"] or ""),
                "predicted_label": rc.primary,
                "confidence": rc.confidence,
                "ambiguous": "true" if rc.ambiguous else "false",
                "recommended_action": rc.recommended_action,
                "etiqueta_ui": spanish_heuristic_bucket_label(rc.primary),
                "evidence": " | ".join(rc.evidence) + (" | " + mart_hint if mart_hint else ""),
                "manual_label": "",
                "notes": "ambiguous=" + str(rc.ambiguous) + ("; " + mart_hint if mart_hint else ""),
            }
        )

    pred_no_alias = sql_predicate_contacto_gmail_source()
    no_resp = mark_no_response_candidates(
        conn,
        canonical_where_sql=pred_no_alias,
        days=days,
        limit=min(500, max(50, limit // 4)),
        internal_domains_lower=internal,
    )
    by_primary["no_response_after_sent"] = len(no_resp)
    for r in no_resp[:15]:
        examples["no_response_after_sent"].append(
            {
                "id": int(r["id"]),
                "date_iso": r.get("date_iso"),
                "folder": r.get("folder"),
                "from_addr": _snippet(r.get("sender"), 120),
                "to_addrs": _snippet(r.get("recipients"), 120),
                "subject": _snippet(r.get("subject"), 160),
                "detected_category": "no_response_after_sent",
                "confidence": r.get("confidence"),
                "recommended_action": recommended_action_for_classification(
                    "no_response_after_sent", str(r.get("confidence") or "weak_signal")
                ),
                "evidence_snippet": r.get("evidence"),
            }
        )

    legacy_note = ""
    if legacy_also:
        legacy_note = (
            "Optional legacy comparison not implemented in this version; "
            "re-run with canonical-only default or extend predicate with OR labdelivery LIKE."
        )

    counts_out = dict(by_primary)
    for _z in ("marketplace_or_procurement_platform", "logistics_or_notification"):
        counts_out.setdefault(_z, 0)

    return {
        "summary": {
            "rows_scanned": len(rows),
            "counts_by_primary": counts_out,
            "ambiguous_rows": ambiguous_n,
            "likely_missed_quote_request": likely_missed_n,
            "supplier_domains_loaded": len(supplier_domains),
            "internal_domains_used": sorted(internal),
            "legacy_flag": legacy_also,
            "legacy_note": legacy_note,
        },
        "examples_by_category": {k: v for k, v in examples.items()},
        "review_csv_rows": review_rows,
        "reliability_notes": {
            "bad_email_or_bounce": "Usually high_confidence when mailer-daemon / postmaster / NDR subject heuristics hit.",
            "marketplace_or_procurement_platform": "Sender/recipient domain ∈ {mercadopublico.cl, wherex.com}; not buyer lead classification.",
            "logistics_or_notification": "Sender/recipient domain ∈ {dhl.com, facebookmail.com, twitter.com}; carrier/social notifications.",
            "cotizacion_sent": "Sent folder + cotización/presupuesto language; high when document_master quote types align or multiple commercial terms.",
            "quote_request_inbound": "Tiered Spanish/English RFQ heuristics (strong/medium/weak); still not ground truth.",
            "university_or_research": "Domain tails (.edu, uchile.cl, …) + name keywords — weak on unknown subdomains.",
            "supplier_or_vendor": "Strong when domain ∈ supplier_master; misses unknown suppliers.",
            "client_or_buyer": "Very weak keyword scan only — needs_manual_review for decisions.",
            "no_response_after_sent": "Overlap on sender/recipients text after sent date; misses BCC/thread drift.",
            "needs_follow_up": "Residual bucket — always review before automation.",
        },
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "email_id",
        "date_iso",
        "folder",
        "from_addr",
        "to_addrs",
        "subject",
        "predicted_label",
        "confidence",
        "ambiguous",
        "recommended_action",
        "etiqueta_ui",
        "evidence",
        "manual_label",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: settings)")
    ap.add_argument("--days", type=int, default=120, help="lookback window on date_iso (default 120)")
    ap.add_argument("--limit", type=int, default=2500, help="max rows to scan (default 2500)")
    ap.add_argument("--json", action="store_true", help="print JSON summary to stdout")
    ap.add_argument("--out", type=Path, default=None, help="write full JSON audit to this path")
    ap.add_argument(
        "--csv-out",
        type=Path,
        default=_ROOT / "reports" / "out" / "qa" / "email_classification_review_sample.csv",
        help="manual review CSV path (default under reports/out/qa/); omit with --no-csv",
    )
    ap.add_argument(
        "--no-csv",
        action="store_true",
        help="do not write the manual review CSV",
    )
    ap.add_argument(
        "--legacy-also",
        action="store_true",
        help="reserved: optional legacy comparison (not implemented; documents intent only)",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = (args.db or settings.resolved_sqlite_path()).expanduser().resolve()
    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    conn = _connect_ro(db_path)
    try:
        payload = run_audit(conn, days=args.days, limit=args.limit, legacy_also=args.legacy_also)
    finally:
        conn.close()

    payload["meta"] = {"sqlite_path": str(db_path), "days": args.days, "limit": args.limit}
    payload["baseline_comparison"] = {
        "reference": _AUDIT_HEURISTIC_BASELINE_V1,
        "current_summary": payload["summary"],
    }

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote JSON: {args.out}", file=sys.stderr)

    if not args.no_csv and args.csv_out:
        _write_csv(args.csv_out, payload["review_csv_rows"])
        print(f"Wrote CSV: {args.csv_out}", file=sys.stderr)

    _emit_baseline_delta(payload["summary"])

    if args.json:
        # stdout: compact summary without huge review rows for operator piping
        slim = {
            "meta": payload["meta"],
            "summary": payload["summary"],
            "reliability_notes": payload["reliability_notes"],
            "baseline_comparison": payload["baseline_comparison"],
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2))
    else:
        s = payload["summary"]
        print(f"SQLite: {db_path}", file=sys.stderr)
        print(f"Rows scanned: {s['rows_scanned']}", file=sys.stderr)
        print("Counts (primary label):", file=sys.stderr)
        for k, v in sorted(s["counts_by_primary"].items(), key=lambda kv: (-int(kv[1]), kv[0])):
            print(f"  {k}: {v}", file=sys.stderr)
        print(f"Ambiguous (multi-tag): {s['ambiguous_rows']}", file=sys.stderr)
        print(f"Inbox commercial-ish sin quote_request fuerte: {s['likely_missed_quote_request']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
