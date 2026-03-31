#!/usr/bin/env python3
"""Structural validation for supplier DeepSearch workbook (no DB writes)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.supplier_workbook import (
    collect_workbook_validation_issues,
    partition_supplier_validation_issues,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate supplier workbook structure.")
    ap.add_argument("--xlsx", "-x", type=Path, required=True)
    ap.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Exit 1 if any warning or error.",
    )
    args = ap.parse_args()
    path = args.xlsx.resolve()
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1
    issues = collect_workbook_validation_issues(path)
    err, warn = partition_supplier_validation_issues(issues)
    for w in warn:
        print(f"WARN {w}")
    for e in err:
        print(f"ERROR {e}")
    if err:
        return 1
    if args.warnings_as_errors and warn:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
