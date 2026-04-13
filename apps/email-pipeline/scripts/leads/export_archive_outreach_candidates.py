#!/usr/bin/env python3
"""Audit/export archive-based outreach candidates (historical `contact_master` source, read-only).

This script does not write to SQLite. It applies the same gate used by lead outreach:
Sent history (`contacto@origenlab.cl` mailbox), suppression, outreach state, supplier/internal/noise.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.archive_outreach_queue import audit_archive_outreach_candidates
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive-based outreach audit/export (contact_master source)")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV (eligible + blocked)")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--gmail-user", type=str, default="", help="Mailbox for Sent-history gate")
    ap.add_argument("--sent-folder", action="append", default=[], help="Repeatable sent folders")
    ap.add_argument("--exclude-domain", action="append", default=[], help="Repeatable blocked domain")
    ap.add_argument("--fetch-cap", type=int, default=20000, help="Rows scanned from contact_master")
    ap.add_argument("--limit", type=int, default=500, help="Max audited rows after dedupe/sort")
    ap.add_argument(
        "--json-summary",
        type=Path,
        default=None,
        help="Optional JSON summary with eligible/blocked counts and reason breakdown",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS
    extra_domains = tuple(args.exclude_domain) if args.exclude_domain else ()

    conn = connect(db_path)
    try:
        audit = audit_archive_outreach_candidates(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            extra_exclude_domains=extra_domains,
            fetch_cap=int(args.fetch_cap),
            limit=int(args.limit),
            strict_contact_graph_noise=True,
        )
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.to_dict() for r in audit.rows]
    fieldnames = list(rows[0].keys()) if rows else [
        "case_id",
        "contact_email",
        "recipient_name",
        "institution_name",
        "domain",
        "contact_total_emails",
        "contact_last_seen_at",
        "contact_confidence_score",
        "contact_quote_email_count",
        "contact_invoice_email_count",
        "contact_purchase_email_count",
        "org_total_emails",
        "org_quote_email_count",
        "org_invoice_email_count",
        "org_purchase_email_count",
        "dormant_signal_count",
        "warmth_score",
        "eligible",
        "reject_reason_code",
    ]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    summary = {
        "rows": len(rows),
        "eligible_count": audit.eligible_count,
        "blocked_count": audit.blocked_count,
        "blocked_by_reason": dict(sorted(audit.blocked_by_reason.items())),
        "gmail_user": gmail_user,
        "db_path": str(db_path),
    }
    print(json.dumps(summary, ensure_ascii=False))

    if args.json_summary:
        args.json_summary.parent.mkdir(parents=True, exist_ok=True)
        args.json_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
