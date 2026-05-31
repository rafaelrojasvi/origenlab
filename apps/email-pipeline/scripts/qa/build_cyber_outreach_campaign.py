#!/usr/bin/env python3
"""Build read-only Cyber outreach review CSVs (no Gmail, no outreach writes).

Outputs under reports/out/active/current/ by default:
  cyber_warm_contacts_review.csv
  cyber_previous_buyers_review.csv
  cyber_net_new_safe_review.csv
  cyber_excluded_blocked.csv
  cyber_same_domain_review.csv
  cyber_top25_recommended.csv
  cyber_campaign_summary.json
  cyber_campaign_report.md
  cyber_email_templates_es.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.campaigns.cyber_outreach_campaign import (
    build_cyber_outreach_campaign,
    write_cyber_campaign_outputs,
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
        help="Directory for Cyber CSVs and report",
    )
    ap.add_argument(
        "--do-not-repeat-csv",
        type=Path,
        default=None,
        help="Optional do_not_repeat_master.csv",
    )
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument("--warm-scan-limit", type=int, default=350)
    ap.add_argument("--net-new-limit", type=int, default=60)
    ap.add_argument(
        "--lead-research-review-csv",
        type=Path,
        default=None,
        help="Phase 10D new_customer_targets_review.csv (default: active/current)",
    )
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
        result = build_cyber_outreach_campaign(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            do_not_repeat_csv=dnr_path,
            lead_research_review_csv=args.lead_research_review_csv,
            warm_archive_scan_limit=args.warm_scan_limit,
            net_new_limit=args.net_new_limit,
        )
    finally:
        conn.close()

    paths = write_cyber_campaign_outputs(result, out_dir)
    elig = result.summary.get("eligible_by_segment") or {}
    print("Cyber outreach campaign (read-only) — no sends, no outreach writes")
    print(f"  DB: {db_path}")
    print(f"  Out: {out_dir}")
    print(f"  Warm elegibles: {elig.get('warm_open', 0)}")
    print(f"  Previous buyers elegibles: {elig.get('previous_buyer_responder', 0)}")
    print(f"  Net-new elegibles: {elig.get('net_new_safe', 0)}")
    print(f"  Net-new Phase 10D: {elig.get('net_new_lead_research', 0)}")
    print(f"  Manual geo review: {elig.get('manual_geo_review', 0)}")
    print(f"  Same-domain review: {elig.get('same_domain_review', 0)}")
    print(f"  Excluded/blocked: {elig.get('excluded_blocked', 0)}")
    print(f"  Top 25 org-deduped: {len(result.top25_deduped)}")
    print(f"  Quality report: {paths['quality_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
