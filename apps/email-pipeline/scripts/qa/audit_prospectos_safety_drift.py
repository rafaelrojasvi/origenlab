#!/usr/bin/env python3
"""Read-only Prospectos safety drift audit (raw lead_research vs operational sidecars).

Does not send email, mutate Gmail, write SQLite/Postgres, or rebuild lead_research tables.

Example::

  uv run python scripts/qa/audit_prospectos_safety_drift.py
  uv run python scripts/qa/audit_prospectos_safety_drift.py --strict
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
from origenlab_email_pipeline.lead_research.prospectos_safety_drift import (
    connect_sqlite_readonly,
    print_headline_counts,
    run_prospectos_safety_drift_audit,
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
        help="Output directory (default: reports/out/active/current/prospectos_safety_drift_<date>)",
    )
    parser.add_argument(
        "--date-label",
        default=None,
        help="Folder date suffix YYYY_MM_DD (default: today UTC)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 when drift exceeds thresholds (for CI guardrails)",
    )
    parser.add_argument(
        "--max-suppressed-raw-mismatch",
        type=int,
        default=None,
        help="Max allowed suppressed-not-raw-blocked rows in --strict (default: 0)",
    )
    parser.add_argument(
        "--max-net-new-blocked",
        type=int,
        default=None,
        help="Max allowed net-new-raw-but-safety-blocked rows in --strict (default: 0)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    sqlite_path = (args.sqlite_path or settings.resolved_sqlite_path()).resolve()

    date_label = args.date_label or date.today().strftime("%Y_%m_%d")
    out_dir = (args.out_dir or (_DEFAULT_ACTIVE / f"prospectos_safety_drift_{date_label}")).resolve()

    max_suppressed = (
        0 if args.max_suppressed_raw_mismatch is None else args.max_suppressed_raw_mismatch
    )
    max_net_new = 0 if args.max_net_new_blocked is None else args.max_net_new_blocked

    conn = connect_sqlite_readonly(sqlite_path)
    try:
        result = run_prospectos_safety_drift_audit(conn, sqlite_path=sqlite_path, out_dir=out_dir)
    finally:
        conn.close()

    print_headline_counts(result.summary, out_dir=out_dir)

    if args.strict:
        code = result.exit_code_strict(
            max_suppressed_raw_mismatch=max_suppressed,
            max_net_new_blocked=max_net_new,
        )
        if code != 0:
            print(
                "STRICT: drift exceeds threshold "
                f"(suppressed_not_raw_blocked<={max_suppressed}, "
                f"net_new_raw_but_safety_blocked<={max_net_new})",
                file=sys.stderr,
            )
        return code
    return result.exit_code_default


if __name__ == "__main__":
    raise SystemExit(main())
