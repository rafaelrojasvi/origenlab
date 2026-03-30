#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.tatiana_copilot.review_summary import (
    load_review_rows,
    summarize_review,
    write_review_outputs,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize manual review scores for Tatiana draft eval")
    ap.add_argument(
        "--eval-dir",
        type=Path,
        default=None,
        help="Folder containing eval_cases.csv (e.g. reports/out/<ts>_tatiana_draft_eval)",
    )
    ap.add_argument(
        "--eval-csv",
        type=Path,
        default=None,
        help="Path to eval_cases.csv directly (overrides --eval-dir)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Where to write review_summary.* (default: <eval-dir>/review_summary)",
    )
    args = ap.parse_args()

    settings = load_settings()
    if args.eval_csv:
        eval_csv = args.eval_csv
        eval_dir = eval_csv.parent
    else:
        eval_dir = args.eval_dir or (settings.resolved_reports_dir() / "latest_tatiana_draft_eval")
        eval_csv = eval_dir / "eval_cases.csv"

    if not eval_csv.is_file():
        print("eval_cases.csv not found:", eval_csv, file=sys.stderr)
        raise SystemExit(1)

    out_dir = args.out_dir or (eval_dir / "review_summary")

    rows = load_review_rows(eval_csv)
    summary = summarize_review(rows)
    write_review_outputs(summary=summary, rows=rows, out_dir=out_dir)
    print(out_dir)


if __name__ == "__main__":
    main()

