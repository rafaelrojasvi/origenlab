#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Read-only inspection of a single commercial deal stored in SQLite.
# Never writes to SQLite. Opens the DB in read-only mode.
# -----------------------------------------------------------------------------
"""Inspect a commercial deal from SQLite — read-only, human-readable report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.commercial.commercial_deal_inspector import (  # noqa: E402
    build_deal_report,
    connect_readonly,
    format_deal_report,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sqlite-db",
        type=Path,
        required=True,
        help="Path to SQLite DB (opened read-only)",
    )
    p.add_argument(
        "--deal-key",
        required=True,
        help="deal_key to inspect",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Machine-readable JSON output (payments still have masked IDs)",
    )
    p.add_argument(
        "--pretty-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-print JSON output (default: on; ignored without --json)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.sqlite_db.expanduser().resolve()

    try:
        conn = connect_readonly(db_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        report = build_deal_report(conn, args.deal_key.strip())
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    if args.output_json:
        indent = 2 if args.pretty_json else None
        sys.stdout.write(
            json.dumps(report, indent=indent, ensure_ascii=False, default=str) + "\n"
        )
    else:
        print(format_deal_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
