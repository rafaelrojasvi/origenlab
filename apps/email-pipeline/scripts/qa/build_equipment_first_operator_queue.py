#!/usr/bin/env python3
"""Build canonical equipment-first operator queue + aligned AB queue."""

from __future__ import annotations

import argparse
from pathlib import Path

from origenlab_email_pipeline.equipment_first_operator_queue import build_all

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports/out/active/current"
DEFAULT_DB = Path("/home/rafael/data/origenlab-email/sqlite/emails.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-suffix", default="20260518")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    stats = build_all(
        reports_dir=args.reports_dir,
        db_path=args.db,
        date_suffix=args.date_suffix,
    )
    for k, v in stats.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
