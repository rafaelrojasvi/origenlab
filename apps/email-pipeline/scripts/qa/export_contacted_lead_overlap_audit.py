#!/usr/bin/env python3
"""Read-only audit: lead / DeepSearch contacts vs Sent history, outreach state, suppressions.

Flags overlaps before importing research CSVs or sending campaigns. Does not modify SQLite,
gate logic, or send mail.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)
from origenlab_email_pipeline.qa.contacted_lead_overlap import (
    PendingResearchCsvStats,
    build_contacted_lead_overlap_audit,
    connect_readonly,
    load_input_research_csv,
    prepare_csv_only_rows,
    print_contacted_lead_overlap_summary,
    summarize_contacted_lead_overlap,
    write_contacted_lead_overlap_csv,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="Output CSV path.")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config).")
    ap.add_argument(
        "--input-research-csv",
        type=Path,
        default=None,
        help="Optional reviewed DeepSearch CSV (pre-import); merges pending emails by lead_id.",
    )
    ap.add_argument("--limit", type=int, default=5000, help="Max rows written after sorting (default 5000).")
    ap.add_argument(
        "--fit",
        type=str,
        default="high_fit,medium_fit",
        help="Comma-separated fit_bucket values (default: high_fit,medium_fit).",
    )
    ap.add_argument(
        "--include-low-fit",
        action="store_true",
        help="Include low_fit rows in addition to --fit values.",
    )
    ap.add_argument("--sample-limit", type=int, default=10, help="Max orgs in terminal top-overlap list (default 10).")
    ap.add_argument("--gmail-user", type=str, default=None, help="Mailbox for Sent scan (default: settings).")
    ap.add_argument(
        "--sent-folder",
        action="append",
        default=[],
        help="Sent folder label (repeatable); default both Gmail labels.",
    )
    args = ap.parse_args()

    if args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2
    if args.sample_limit < 1:
        print("--sample-limit must be >= 1", file=sys.stderr)
        return 2

    fits = [x.strip() for x in str(args.fit).split(",") if x.strip()]
    if args.include_low_fit and "low_fit" not in fits:
        fits.append("low_fit")
    if not fits:
        print("--fit must list at least one bucket", file=sys.stderr)
        return 2

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite file not found: {db_path}", file=sys.stderr)
        return 1

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(tuple(args.sent_folder))

    pending_by_lead: dict[str, str] = {}
    csv_only_rows: list[dict[str, str]] = []
    pending_stats = PendingResearchCsvStats()
    if args.input_research_csv is not None:
        if not args.input_research_csv.is_file():
            print(f"Input CSV not found: {args.input_research_csv}", file=sys.stderr)
            return 1
        pending_by_lead, raw_csv, pending_stats = load_input_research_csv(args.input_research_csv)
        csv_only_rows = prepare_csv_only_rows(raw_csv, db_path)

    conn = connect_readonly(db_path)
    try:
        rows_out = build_contacted_lead_overlap_audit(
            conn,
            fit_buckets=tuple(fits),
            pending_by_lead=pending_by_lead,
            csv_only_rows=csv_only_rows,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
        )
    finally:
        conn.close()

    summary = summarize_contacted_lead_overlap(
        rows_out,
        pending_stats=pending_stats,
        sample_limit=int(args.sample_limit),
    )
    rows_written = write_contacted_lead_overlap_csv(args.out, rows_out, limit=int(args.limit))
    print_contacted_lead_overlap_summary(
        summary,
        out_path=args.out,
        rows_written=rows_written,
        sample_limit=int(args.sample_limit),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
