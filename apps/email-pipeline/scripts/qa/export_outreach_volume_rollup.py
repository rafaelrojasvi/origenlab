#!/usr/bin/env python3
"""Read-only rollup: unique outreach / Sent / contacted volume by source.

Aggregates Gmail Sent (SQLite ``emails``), ``outreach_contact_state``, send manifests,
and known marketing CSVs under ``reports/out/active``. Does not modify the database,
send mail, or change gate logic.
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
from origenlab_email_pipeline.qa.outreach_volume_rollup import build_outreach_volume_rollup


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--reports-out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active",
        help="Root for campaign reports (default: reports/out/active under app)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for rollup CSV + JSON (default: <reports-out-dir>/current)",
    )
    ap.add_argument("--gmail-user", default=None, help="Override Gmail mailbox for Sent scan")
    ap.add_argument("--sent-folder", action="append", default=[], help="Sent folder label (repeatable)")
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or Path(settings.sqlite_path)
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir or (args.reports_out_dir / "current")
    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    result = build_outreach_volume_rollup(
        db_path=db_path,
        reports_out_dir=args.reports_out_dir,
        out_dir=out_dir,
        repo_root=_ROOT,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
    )

    print("Outreach volume rollup (read-only)")
    print(f"  db: {db_path}")
    print(f"  Gmail Sent unique recipients: {result.sent_email_count:,}")
    print(f"  outreach_contact_state (contacted|replied|snoozed) unique: {result.state_email_count:,}")
    print(
        "  Known marketing CSV union (dedup|outreach_contacted|chile_institutional*|deepsearch*): "
        f"{result.marketing_union_count:,}"
    )
    print(f"  Overlap Sent ∩ contacted_state: {result.overlap_sent_and_state:,}")
    print(
        "  Possible missing state marks (in Sent, not in contacted_state): "
        f"{result.sent_not_state_count:,}"
    )
    print(
        "  Possible missing Sent ingest (in contacted_state, not in Sent): "
        f"{result.state_not_sent_count:,}"
    )
    print("  Top sources by unique_email_count:")
    for r in result.top_sources[:8]:
        print(
            f"    - {r['unique_email_count']:>6}  {r['source_kind']}/{r['source_name']}  "
            f"{r['file_path_or_db_source']}"
        )
    print(f"Wrote: {result.rollup_csv_path}")
    print(f"Wrote: {result.summary_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
