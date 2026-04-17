#!/usr/bin/env python3
"""Audit-only export of archive-based outreach candidates (``contact_master`` source, read-only).

**Deprecated as a primary operator path.** Use the canonical archive CLI instead::

    uv run python scripts/leads/build_archive_send_batch.py --audit-only --out-dir <dir> ...

This script remains as a thin wrapper around the same audit logic for custom ``--out``
paths and backward-compatible automation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.archive_outreach_queue import ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO
from origenlab_email_pipeline.archive_send_batch_builder import (
    run_archive_outreach_audit,
    write_archive_audit_csv_and_summary,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outbound_core import (
    build_outbound_run_envelope,
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
    sent_folder_defaults_were_used,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Audit-only archive outreach export (wrapper). "
            "Prefer: scripts/leads/build_archive_send_batch.py --audit-only"
        )
    )
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV (eligible + blocked)")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--gmail-user", type=str, default="", help="Mailbox for Sent-history gate")
    ap.add_argument("--sent-folder", action="append", default=[], help="Repeatable sent folders")
    ap.add_argument("--exclude-domain", action="append", default=[], help="Repeatable blocked domain")
    ap.add_argument("--fetch-cap", type=int, default=20000, help="Rows scanned from contact_master")
    ap.add_argument("--limit", type=int, default=500, help="Max audited rows after dedupe/sort")
    ap.add_argument(
        "--archive-candidate-sort",
        choices=("company_intro", "company_intro_fresh_last_seen", "legacy"),
        default=ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
        help="Candidate ordering before gate audit (default: company_intro).",
    )
    ap.add_argument(
        "--json-summary",
        type=Path,
        default=None,
        help="Optional JSON summary with eligible/blocked counts and reason breakdown",
    )
    args = ap.parse_args()

    print(
        "NOTE: Prefer canonical: uv run python scripts/leads/build_archive_send_batch.py "
        "--audit-only --out-dir <dir>",
        file=sys.stderr,
    )

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_explicit = args.gmail_user.strip() if args.gmail_user and str(args.gmail_user).strip() else None
    gmail_user = resolve_outbound_gmail_user(settings, explicit=gmail_explicit)
    sent_folder_defaults_used = sent_folder_defaults_were_used(args.sent_folder)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)
    extra_domains = tuple(args.exclude_domain) if args.exclude_domain else ()
    created_at_utc = datetime.now(timezone.utc).isoformat()

    conn = connect(db_path)
    try:
        audit = run_archive_outreach_audit(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            extra_exclude_domains=extra_domains,
            fetch_cap=int(args.fetch_cap),
            audit_limit=int(args.limit),
            strict_contact_graph_noise=True,
            archive_candidate_sort=str(args.archive_candidate_sort),
        )
    finally:
        conn.close()

    artifacts: dict[str, str] = {"audit_csv": str(args.out.resolve())}
    if args.json_summary:
        artifacts["audit_summary_json"] = str(args.json_summary.resolve())
    outbound_run = build_outbound_run_envelope(
        lane="archive",
        gmail_user=gmail_user,
        sqlite_path=str(db_path),
        sent_folders=sent_folders,
        sent_folder_defaults_used=sent_folder_defaults_used,
        strict_contact_graph_noise=True,
        extra_exclude_domains=extra_domains,
        created_at_utc=created_at_utc,
        artifact_paths=artifacts,
        counts={
            "archive_audited_rows": len(audit.rows),
            "archive_eligible_rows": int(audit.eligible_count),
            "archive_blocked_rows": int(audit.blocked_count),
        },
    )
    summary = write_archive_audit_csv_and_summary(
        audit=audit,
        audit_csv_path=args.out,
        audit_summary_json_path=args.json_summary,
        gmail_user=gmail_user,
        db_path=db_path,
        outbound_run=outbound_run,
    )

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
