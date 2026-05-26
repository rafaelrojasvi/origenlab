#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Build a commercial_deal* insert/update plan from operator preview JSON.
# Default: dry-run only (stdout JSON). No SQLite writes without explicit --apply
# (apply path is fail-closed until operator approval).
# -----------------------------------------------------------------------------
"""Promote SERVA/CEAF (or future) commercial deal preview into ledger tables — dry-run."""

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

from origenlab_email_pipeline.commercial.commercial_deal_promotion import (  # noqa: E402
    APPLY_NOT_IMPLEMENTED_MSG,
    build_plan_for_deal_key,
    validate_apply_args,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--deal-key",
        required=True,
        help="Deal key matching reports/.../commercial_deals_preview/<deal-key>.json",
    )
    p.add_argument(
        "--preview-json",
        type=Path,
        default=None,
        help="Override preview JSON path (default: active/current commercial_deals_preview)",
    )
    p.add_argument(
        "--sqlite-db",
        type=Path,
        default=None,
        help="Optional SQLite path for idempotency hints only (read-only in dry-run)",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write plan JSON to path (also prints summary to stdout)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write plan to SQLite (not implemented — requires explicit guard flags)",
    )
    p.add_argument(
        "--i-understand-this-writes-sqlite",
        action="store_true",
        help="Required with --apply",
    )
    return p


def _optional_ro_conn(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.is_file():
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    err = validate_apply_args(
        apply=args.apply,
        sqlite_db=args.sqlite_db,
        deal_key=args.deal_key,
        understand_writes=args.i_understand_this_writes_sqlite,
    )
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    if args.apply:
        print(f"ERROR: {APPLY_NOT_IMPLEMENTED_MSG}", file=sys.stderr)
        return 3

    conn: sqlite3.Connection | None = None
    if args.sqlite_db is not None:
        db_path = args.sqlite_db.expanduser().resolve()
        conn = _optional_ro_conn(db_path)
        if conn is None:
            print(f"WARN: --sqlite-db not found; idempotency hints assume insert: {db_path}", file=sys.stderr)

    try:
        plan = build_plan_for_deal_key(
            args.deal_key.strip(),
            preview_path=args.preview_json,
            pipeline_root=_ROOT,
            conn=conn,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()

    report = plan.to_dict()
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.json_out}")

    print(f"DRY-RUN commercial deal promotion plan for {plan.deal_key}")
    print(f"deal_action={plan.deal_action} schema_version={plan.schema_version}")
    print(f"counts={json.dumps(plan.counts, ensure_ascii=False)}")
    if not args.json_out:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
