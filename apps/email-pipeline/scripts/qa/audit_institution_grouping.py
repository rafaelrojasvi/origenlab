#!/usr/bin/env python3
"""Read-only institution / organization grouping audit (Chile-focused).

Does not mutate Gmail, SQLite, Postgres, or merge legacy contacts.

Example::

  uv run python scripts/qa/audit_institution_grouping.py
  uv run python scripts/qa/audit_institution_grouping.py --date-label 2026_06_01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.lead_research.institution_grouping_audit import (
    connect_sqlite_readonly,
    print_headline_counts,
    run_institution_grouping_audit,
)

_DEFAULT_ACTIVE = _ROOT / "reports/out/active/current"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        "--db",
        type=Path,
        dest="sqlite_path",
        default=None,
        help="SQLite path (default: ORIGENLAB_SQLITE_PATH / settings)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: reports/out/active/current/institution_grouping_audit_<date>)",
    )
    parser.add_argument(
        "--date-label",
        default=None,
        help="Folder date suffix YYYY_MM_DD (default: today)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    sqlite_path = (args.sqlite_path or settings.resolved_sqlite_path()).resolve()
    date_label = args.date_label or date.today().strftime("%Y_%m_%d")
    out_dir = (args.out_dir or (_DEFAULT_ACTIVE / f"institution_grouping_audit_{date_label}")).resolve()

    conn = connect_sqlite_readonly(sqlite_path)
    try:
        result = run_institution_grouping_audit(conn, sqlite_path=sqlite_path, out_dir=out_dir)
    finally:
        conn.close()

    print_headline_counts(result.summary, out_dir=out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
