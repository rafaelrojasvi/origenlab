#!/usr/bin/env python3
"""Build read-only Presentación OrigenLab review CSVs (no Gmail, no outreach writes).

Outputs under reports/out/active/current/ by default:
  presentacion_origenlab_send_now_review.csv
  presentacion_origenlab_same_domain_review.csv
  presentacion_origenlab_hold_active_cases.csv
  presentacion_origenlab_missing_email_research.csv
  presentacion_origenlab_messages.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.campaigns.presentacion_origenlab_campaign import (
    build_presentacion_origenlab_review,
    write_presentacion_outputs,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.leads.contacted_universe_audit import connect_readonly
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default from settings)")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
        help="Directory for Presentación CSVs and messages",
    )
    ap.add_argument(
        "--cyberday-log",
        type=Path,
        default=None,
        help="cyber_production_send_log.json (default: out-dir)",
    )
    ap.add_argument(
        "--do-not-repeat-csv",
        type=Path,
        default=None,
        help="Optional do_not_repeat_master.csv",
    )
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir.resolve()
    dnr = args.do_not_repeat_csv or (out_dir / "do_not_repeat_master.csv")
    dnr_path = dnr if dnr.is_file() else None
    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    conn = connect_readonly(db_path)
    try:
        result = build_presentacion_origenlab_review(
            conn,
            out_dir=out_dir,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            cyberday_log=args.cyberday_log,
            do_not_repeat_csv=dnr_path,
        )
    finally:
        conn.close()

    paths = write_presentacion_outputs(result, out_dir)
    counts = result.summary.get("counts") or {}
    print("Presentación OrigenLab (read-only) — no sends, no outreach writes")
    print(f"  DB: {db_path}")
    print(f"  Out: {out_dir}")
    print(f"  CyberDay excluded: {result.summary.get('cyberday_excluded_count', 0)}")
    print(f"  Send-now review: {counts.get('send_now_review', 0)}")
    print(f"  Same-domain review: {counts.get('same_domain_review', 0)}")
    print(f"  Hold active cases: {counts.get('hold_active_cases', 0)}")
    print(f"  Missing email research: {counts.get('missing_email_research', 0)}")
    print(f"  Messages: {paths['messages']}")
    print("  Top recommended:")
    for i, item in enumerate(result.summary.get("top_recommended") or [], start=1):
        print(
            f"    {i}. {item.get('email')} — {item.get('organization')} "
            f"(score {item.get('priority_score')})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
