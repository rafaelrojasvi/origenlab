#!/usr/bin/env python3
"""Process DeepSearch prospect CSVs into safe new-customer review lists (Phase 10B).

Read-only: no Gmail, no SQLite writes, no outreach mutations.

Inputs:
  reports/in/leads/new_customer_research/*.csv  (monorepo root, default)
  reports/out/active/current/*_for_exclusion.csv  (Phase 10A.1)

Outputs (under apps/email-pipeline/reports/out/active/current by default):
  new_customer_targets_review.csv
  new_customer_targets_blocked.csv
  new_customer_targets_top25.md
  new_customer_targets_summary.md
  follow_up_candidates_top25.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[2]
_MONOREPO = _PIPELINE.parents[1]
if str(_PIPELINE / "src") not in sys.path:
    sys.path.insert(0, str(_PIPELINE / "src"))

from origenlab_email_pipeline.leads.new_customer_research import run_process


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input-dir",
        type=Path,
        default=_MONOREPO / "reports" / "in" / "leads" / "new_customer_research",
        help="Directory with DeepSearch CSV files",
    )
    ap.add_argument(
        "--exclusion-dir",
        type=Path,
        default=_PIPELINE / "reports" / "out" / "active" / "current",
        help="Phase 10A.1 exclusion CSV directory",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_PIPELINE / "reports" / "out" / "active" / "current",
        help="Output directory for review CSVs and markdown",
    )
    args = ap.parse_args(argv)

    if not args.input_dir.is_dir():
        print(f"Input directory not found: {args.input_dir}", file=sys.stderr)
        return 1

    result = run_process(args.input_dir, args.exclusion_dir, args.out_dir)
    s = result.summary
    print("DeepSearch new-customer processing (read-only)")
    print(f"  Input files: {len(result.input_files)}")
    for f in result.input_files:
        print(f"    - {f}")
    print(f"  Rows after dedupe: {s.get('total_rows_processed', 0):,}")
    print(f"  Review: {s.get('review_rows', 0):,}")
    print(f"  Blocked: {s.get('blocked_rows', 0):,}")
    print(f"  Net-new safe: {s.get('net_new_safe_count', 0):,}")
    print(f"  Public tender review: {s.get('public_tender_review_count', 0):,}")
    print(f"  Wrote outputs under: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
