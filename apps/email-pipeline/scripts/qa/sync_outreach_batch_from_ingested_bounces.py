#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): --apply writes contact_email_suppression and optionally
# outreach_contact_state. Review JSON evidence before --apply.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Classify a manual outreach batch using **ingested** NDR/bounce mail in SQLite.

Workflow::

  # 1) Pull recent Workspace mail (INBOX catches most NDRs; Sent optional for memory)
  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --since-days 21 --folder INBOX
  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --since-days 21 --folder '[Gmail]/Sent Mail'

  # 2) Preview (JSON): bad = batch addresses mentioned inside bounce-classified rows
  uv run python scripts/qa/sync_outreach_batch_from_ingested_bounces.py \\
    --batch-file reports/out/active/archive_send_batch_after_domain_expand/archive_manual_send_candidates_v3_to.txt \\
    --since-days 21

  # 3) Apply: write ``contact_email_suppression`` for NDR/body matches only
  uv run python scripts/qa/sync_outreach_batch_from_ingested_bounces.py \\
    --batch-file ... --since-days 21 --apply --updated-by rafael

  # Optional: also set outreach_contact_state=contacted for batch addresses not matched to an NDR
  # (only after you accept that “no matching NDR in SQLite” means “delivered OK” for your run)
  uv run python scripts/qa/sync_outreach_batch_from_ingested_bounces.py \\
    --batch-file ... --since-days 21 --apply --mark-contacted-for-remaining --updated-by rafael

Heuristic: only flags an address when it appears in your batch file **and** in the body/subject
of a message classified as bounce/NDR. Review ``evidence`` in the JSON before ``--apply``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_email_suppression import fetch_contact_email_suppression_row
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outreach_ingest_sync import (
    BounceBatchScanResult,
    apply_bounce_batch_scan,
    format_scan_summary,
    scan_batch_against_ingested_bounces_from_text,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--batch-file",
        type=Path,
        required=True,
        help="UTF-8 file: one mailbox per line (same style as mark_outreach_state batch files).",
    )
    ap.add_argument(
        "--since-days",
        type=int,
        default=30,
        help="Only consider ingested rows with date_iso on/after (UTC today − N days). Default: 30.",
    )
    ap.add_argument(
        "--source-like",
        default="gmail:%",
        help="SQL LIKE filter on emails.source_file (default: gmail:%%).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write DB updates (otherwise JSON preview only).",
    )
    ap.add_argument(
        "--mark-contacted-for-remaining",
        action="store_true",
        help="With --apply, also set outreach_contact_state=contacted for batch addresses not flagged as bad.",
    )
    ap.add_argument(
        "--updated-by",
        default="sync_outreach_batch_from_ingested_bounces.py",
        help="Audit column for suppression + outreach writes.",
    )
    ap.add_argument(
        "--suppression-source",
        default="sync_outreach_batch_from_ingested_bounces",
        help="contact_email_suppression.suppression_source",
    )
    ap.add_argument(
        "--outreach-source",
        default="sync_outreach_batch_from_ingested_bounces",
        help="outreach_contact_state.source for contacted rows",
    )
    ap.add_argument(
        "--outreach-notes",
        default=None,
        help="Optional outreach_contact_state.notes for contacted rows",
    )
    ap.add_argument(
        "--include-evidence",
        action="store_true",
        help="Include per-message evidence list in JSON (can be long).",
    )
    args = ap.parse_args(argv)

    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("SQLite file not found:", db_path, file=sys.stderr)
        return 1
    if not args.batch_file.is_file():
        print("Batch file not found:", args.batch_file, file=sys.stderr)
        return 1

    text = args.batch_file.read_text(encoding="utf-8")
    conn = connect(db_path)
    try:
        scan = scan_batch_against_ingested_bounces_from_text(
            conn,
            text,
            since_days=int(args.since_days),
            source_like=str(args.source_like),
        )
        summary = format_scan_summary(scan)
        pre_suppressed_good = [e for e in scan.good if fetch_contact_email_suppression_row(conn, e)]
        summary["good_already_suppressed"] = pre_suppressed_good

        out: dict[str, object] = dict(summary)
        if args.include_evidence:
            out["evidence"] = scan.evidence

        if args.apply:
            good_filtered = [e for e in scan.good if e not in pre_suppressed_good]
            merged_batch = sorted(set(scan.bad) | set(good_filtered))
            scan_apply = BounceBatchScanResult(batch=merged_batch, bad=scan.bad, evidence=scan.evidence)
            apply_result = apply_bounce_batch_scan(
                conn,
                scan_apply,
                updated_by=args.updated_by,
                suppression_source=args.suppression_source,
                outreach_source=args.outreach_source,
                outreach_notes=args.outreach_notes,
                mark_contacted_for_good=bool(args.mark_contacted_for_remaining),
            )
            conn.commit()
            out["apply"] = apply_result
            out["skipped_contacted_already_suppressed"] = pre_suppressed_good

        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
