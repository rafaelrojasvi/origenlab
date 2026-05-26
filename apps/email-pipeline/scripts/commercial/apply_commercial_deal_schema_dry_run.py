#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Commercial deal ledger DDL — dry-run (in-memory) or explicit --apply on a SQLite file.
# Does not seed data, Gmail, Postgres, or wire sqlite_migrate.
# -----------------------------------------------------------------------------
"""Apply commercial_deal_* schema (v1.1.0) — dry-run by default."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.commercial.commercial_deal_schema import (  # noqa: E402
    COMMERCIAL_DEAL_SCHEMA_VERSION,
    COMMERCIAL_DEAL_TABLE_NAMES,
    commercial_deal_tables_exist,
    count_commercial_deal_indexes,
    ensure_commercial_deal_tables,
    foreign_key_check_ok,
    list_commercial_deal_tables,
)


def _run_plan(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_commercial_deal_tables(conn)
    fk_ok = foreign_key_check_ok(conn)
    return {
        "schema_version": COMMERCIAL_DEAL_SCHEMA_VERSION,
        "tables": list(list_commercial_deal_tables()),
        "table_count": len(COMMERCIAL_DEAL_TABLE_NAMES),
        "tables_exist": commercial_deal_tables_exist(conn),
        "index_count": count_commercial_deal_indexes(conn),
        "foreign_key_check_ok": fk_ok,
        "applied_to_disk": False,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sqlite-db",
        type=Path,
        default=None,
        help="SQLite file path (required with --apply)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write DDL to --sqlite-db (additive CREATE IF NOT EXISTS only)",
    )
    p.add_argument("--json-out", type=Path, default=None, help="Write result JSON to path")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.apply and args.sqlite_db is None:
        print("ERROR: --apply requires --sqlite-db PATH", file=sys.stderr)
        return 2

    if args.apply:
        db_path = args.sqlite_db.expanduser().resolve()
        if not db_path.parent.is_dir():
            print(f"ERROR: parent directory missing: {db_path.parent}", file=sys.stderr)
            return 2
        conn = sqlite3.connect(str(db_path))
        try:
            report = _run_plan(conn)
            report["applied_to_disk"] = True
            report["sqlite_db"] = str(db_path)
        finally:
            conn.close()
        print(f"APPLIED schema {COMMERCIAL_DEAL_SCHEMA_VERSION} to {db_path}")
    else:
        conn = sqlite3.connect(":memory:")
        try:
            report = _run_plan(conn)
        finally:
            conn.close()
        print(f"DRY-RUN schema {COMMERCIAL_DEAL_SCHEMA_VERSION} (in-memory only; no file modified)")

    print(f"tables ({report['table_count']}): {', '.join(report['tables'])}")
    print(f"index_count={report['index_count']}")
    print(f"foreign_key_check_ok={report['foreign_key_check_ok']}")
    print(f"tables_exist={report['tables_exist']}")

    if not report["foreign_key_check_ok"]:
        print("ERROR: PRAGMA foreign_key_check reported violations", file=sys.stderr)
        return 1

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
