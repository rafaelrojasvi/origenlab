#!/usr/bin/env python3
"""
Generate business filter summary and artifacts from emails.sqlite.
Tags each email with business_filter rules and writes:
  - business_filter_summary.json
  - business_only_sample.json
  - category_counts.csv
  - sender_domain_by_view.csv

  uv run python scripts/reports/generate_business_filter_report.py
  uv run python scripts/reports/generate_business_filter_report.py --out reports/out/my_run --limit 50000
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.email_business_filters import VIEW_NAMES, run_filter_pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Business filter report: tag emails and write artifacts")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="Output directory (default: reports/run_<timestamp>)")
    ap.add_argument("--limit", type=int, default=None, help="Max emails to process (default: all)")
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--sample-size", type=int, default=500, help="Max rows in business_only_sample.json")
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    out_dir = args.out or (settings.resolved_reports_dir() / "business_filter_run")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Business filter pass:", db_path, f"(limit={args.limit or 'all'})")
    summary, business_sample, domain_by_view = run_filter_pass(
        db_path, args.limit, args.top_n, args.sample_size
    )

    # business_filter_summary.json
    out_summary = {**summary, "db": str(db_path.resolve())}
    (out_dir / "business_filter_summary.json").write_text(
        json.dumps(out_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Wrote:", out_dir / "business_filter_summary.json")

    # business_only_sample.json
    (out_dir / "business_only_sample.json").write_text(
        json.dumps(business_sample, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Wrote:", out_dir / "business_only_sample.json")

    # category_counts.csv
    with (out_dir / "category_counts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "count"])
        for cat, count in sorted(summary["primary_category_counts"].items(), key=lambda x: -x[1]):
            w.writerow([cat, count])
    print("Wrote:", out_dir / "category_counts.csv")

    # sender_domain_by_view.csv (one row per view-domain-count)
    with (out_dir / "sender_domain_by_view.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["view", "domain", "count"])
        for view in VIEW_NAMES:
            for item in domain_by_view[view]:
                w.writerow([view, item["domain"], item["count"]])
    print("Wrote:", out_dir / "sender_domain_by_view.csv")

    print("Done. View counts:", summary["view_counts"])


if __name__ == "__main__":
    main()
