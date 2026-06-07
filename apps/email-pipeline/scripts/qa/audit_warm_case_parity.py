#!/usr/bin/env python3
"""Read-only warm-case parity audit between SQLite and Postgres mirror API exports.

Does not call live APIs, mutate SQLite/Postgres/Gmail, or approve sends.

Example::

  curl -sS 'http://127.0.0.1:8001/cases/warm' > /tmp/warm_sqlite.json
  # Run API against Postgres mirror and export again:
  curl -sS 'http://127.0.0.1:8001/cases/warm' > /tmp/warm_postgres.json

  uv run python scripts/qa/audit_warm_case_parity.py \\
    --sqlite-json /tmp/warm_sqlite.json \\
    --postgres-json /tmp/warm_postgres.json \\
    --out-dir reports/out/active/current/warm_case_parity_audit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.qa.warm_case_parity import (
    format_parity_summary,
    run_warm_case_parity_audit,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-json",
        type=Path,
        required=True,
        help="Exported GET /cases/warm JSON when API uses SQLite backend",
    )
    parser.add_argument(
        "--postgres-json",
        type=Path,
        required=True,
        help="Exported GET /cases/warm JSON when API uses Postgres mirror backend",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Optional output directory for CSV/JSON artifacts "
            "(default: only print stdout summary)"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    sqlite_json = args.sqlite_json.resolve()
    postgres_json = args.postgres_json.resolve()
    if not sqlite_json.is_file():
        print(f"sqlite json not found: {sqlite_json}", file=sys.stderr)
        return 2
    if not postgres_json.is_file():
        print(f"postgres json not found: {postgres_json}", file=sys.stderr)
        return 2

    out_dir = args.out_dir.resolve() if args.out_dir is not None else None
    result = run_warm_case_parity_audit(
        sqlite_json=sqlite_json,
        postgres_json=postgres_json,
        out_dir=out_dir,
    )
    print(format_parity_summary(result))
    if out_dir is not None:
        print(f"\nWrote parity artifacts under: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
