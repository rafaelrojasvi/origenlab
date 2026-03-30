#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.tatiana_copilot.pilot_review_summary import (
    summarize_pilot_review,
    validate_pilot_review_csv_headers,
    write_pilot_review_outputs,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Read pilot_review.csv and write pilot_review_summary.{json,md} "
            "(inputs are read-only; outputs overwrite summary files in --out-dir)."
        )
    )
    ap.add_argument(
        "--pilot-dir",
        type=Path,
        default=None,
        help=(
            "Folder from run_tatiana_pilot_batch (contains pilot_review.csv). "
            "Default: REPORTS_DIR/latest_tatiana_pilot_batch (symlink updated each pilot run)."
        ),
    )
    ap.add_argument(
        "--review-csv",
        type=Path,
        default=None,
        help="Path to pilot_review.csv (overrides --pilot-dir)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Where to write pilot_review_summary.* (default: <pilot-dir>)",
    )
    args = ap.parse_args()

    settings = load_settings()
    if args.review_csv:
        csv_path = args.review_csv
        pilot_dir = args.pilot_dir or csv_path.parent
    else:
        pilot_dir = args.pilot_dir or (settings.resolved_reports_dir() / "latest_tatiana_pilot_batch")
        csv_path = pilot_dir / "pilot_review.csv"

    if not csv_path.is_file():
        print("pilot_review.csv not found:", csv_path, file=sys.stderr)
        raise SystemExit(1)

    missing = validate_pilot_review_csv_headers(csv_path)
    if missing:
        print("WARN: pilot_review.csv missing columns:", ", ".join(missing), file=sys.stderr)

    summary = summarize_pilot_review(csv_path)
    out_dir = (args.out_dir or pilot_dir).resolve()
    write_pilot_review_outputs(summary=summary, out_dir=out_dir)
    rec = summary.get("recommendation") or {}
    rec_label = rec.get("label") or "n/a"
    counts = summary.get("counts") or {}
    total = counts.get("total_cases", 0)
    reviewed = counts.get("reviewed_cases", 0)
    print(f"Wrote {out_dir / 'pilot_review_summary.json'}", file=sys.stdout)
    print(f"Wrote {out_dir / 'pilot_review_summary.md'}", file=sys.stdout)
    print(
        f"Summary: {reviewed}/{total} cases reviewed · recommendation={rec_label}",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()
