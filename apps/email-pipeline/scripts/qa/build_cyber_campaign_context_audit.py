#!/usr/bin/env python3
"""Read-only Cyber context audit before send (open-quote safety).

Outputs under reports/out/active/current/ by default:
  cyber_send_now_generic_review.csv
  cyber_send_now_warm_followup_review.csv
  cyber_do_not_send_active_cases.csv
  cyber_manual_review_open_quotes.csv
  cyber_campaign_context_audit.md

Requires existing Cyber campaign CSVs (run build_cyber_outreach_campaign.py first).
No Gmail sends · no outreach-state writes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.campaigns.cyber_campaign_context_audit import (
    audit_cyber_top25,
    write_cyber_context_audit_outputs,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.leads.contacted_universe_audit import connect_readonly


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default from settings)")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
        help="Directory with Cyber CSVs and audit outputs",
    )
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir.resolve()
    top25 = out_dir / "cyber_top25_org_deduped.csv"
    if not top25.is_file():
        print(
            f"Missing {top25.name}. Run build_cyber_outreach_campaign.py first.",
            file=sys.stderr,
        )
        return 1

    conn = connect_readonly(db_path)
    try:
        result = audit_cyber_top25(conn, out_dir=out_dir)
    finally:
        conn.close()

    summary_path = out_dir / "cyber_campaign_summary.json"
    paths = write_cyber_context_audit_outputs(
        result,
        out_dir,
        campaign_summary_path=summary_path if summary_path.is_file() else None,
    )
    s = result.summary
    print("Cyber context audit (read-only) — no sends, no outreach writes")
    print(f"  DB: {db_path}")
    print(f"  Out: {out_dir}")
    print(f"  Top25 audited: {s.get('top25_count', 0)}")
    print(f"  Generic Cyber (A): {s.get('send_now_generic', 0)}")
    print(f"  Warm follow-up (B): {s.get('send_now_warm_followup', 0)}")
    print(f"  Do not send (C): {s.get('do_not_send_active_or_blocked', 0)}")
    print(f"  Manual review (D): {s.get('manual_review', 0)}")
    print(f"  Report: {paths['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
