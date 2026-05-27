#!/usr/bin/env python3
"""Read-only audit: who OrigenLab has already contacted (no-repeat prospecting foundation).

Does not send email, mutate Gmail, or write SQLite/Postgres.

Outputs under reports/out/active/current/:
  contacted_universe_summary.json
  contacted_universe_summary.md
  contacted_universe_contacts.csv
  contacted_universe_domains.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.leads.contacted_universe_audit import (
    build_contacted_universe,
    connect_readonly,
    write_contacted_universe_outputs,
)
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default from settings)")
    ap.add_argument(
        "--reports-out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: <reports-out-dir>/current)",
    )
    ap.add_argument(
        "--do-not-repeat-csv",
        type=Path,
        default=None,
        help="Optional do_not_repeat_master.csv (default: <out-dir>/do_not_repeat_master.csv)",
    )
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir or (args.reports_out_dir / "current")
    dnr_csv = args.do_not_repeat_csv or (out_dir / "do_not_repeat_master.csv")
    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    conn = connect_readonly(db_path)
    try:
        result = build_contacted_universe(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            do_not_repeat_csv=dnr_csv if dnr_csv.is_file() else None,
        )
    finally:
        conn.close()

    paths = write_contacted_universe_outputs(result, out_dir)
    s = result.summary
    print("Contacted universe audit (read-only)")
    print(f"  Sent rows (contacto): {s.get('total_sent_email_rows', 0):,}")
    print(f"  Unique outbound emails: {s.get('unique_outbound_recipient_emails', 0):,}")
    print(f"  Unique outbound domains: {s.get('unique_outbound_recipient_domains', 0):,}")
    print(f"  Bounced emails: {s.get('bounced_recipient_emails', 0):,}")
    print(f"  Suppressed contacts: {s.get('suppressed_contacts', 0):,}")
    print(f"  Follow-up candidates: {s.get('contacts_eligible_for_follow_up', 0):,}")
    print(f"  Blocked from outreach: {s.get('contacts_blocked_from_outreach', 0):,}")
    print(f"  Universe contacts (CSV rows): {s.get('total_universe_contacts', 0):,}")
    for label, path in paths.items():
        print(f"Wrote {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
