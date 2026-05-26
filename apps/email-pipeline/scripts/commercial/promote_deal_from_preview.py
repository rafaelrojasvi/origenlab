#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Build a commercial_deal* insert/update plan from operator preview JSON.
# Default: dry-run only (stdout = JSON). --apply writes to backup/dev SQLite only.
# -----------------------------------------------------------------------------
"""Promote SERVA/CEAF (or future) commercial deal preview into ledger tables."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.commercial.commercial_deal_promotion import (  # noqa: E402
    apply_deal_promotion_plan,
    build_plan_for_deal_key,
    connect_sqlite_rw,
    validate_apply_args,
    validate_sqlite_apply_target,
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
        help="SQLite path (read-only hints in dry-run; required for --apply)",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write plan/result JSON to path (no JSON on stdout when set)",
    )
    p.add_argument(
        "--dry-run-json-out",
        type=Path,
        default=None,
        help="Alias for --json-out (dry-run plan file)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write plan to --sqlite-db (backup/dev only; requires explicit guard)",
    )
    p.add_argument(
        "--i-understand-this-writes-sqlite",
        action="store_true",
        help="Required with --apply",
    )
    p.add_argument(
        "--summary",
        action="store_true",
        help="Print human-readable summary to stderr (dry-run or after --apply)",
    )
    p.add_argument(
        "--pretty-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-print JSON written to stdout or --json-out (default: on)",
    )
    p.add_argument(
        "--allow-production-sqlite",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return p


def _optional_ro_conn(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.is_file():
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _json_text(payload: dict[str, Any], *, pretty: bool) -> str:
    if pretty:
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _write_json_file(path: Path, payload: dict[str, Any], *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload, pretty=pretty), encoding="utf-8")


def _print_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _print_dry_run_summary(plan_deal_key: str, plan_action: str, schema_version: str, counts: dict[str, int]) -> None:
    _print_stderr(f"DRY-RUN commercial deal promotion plan for {plan_deal_key}")
    _print_stderr(f"deal_action={plan_action} schema_version={schema_version}")
    _print_stderr(f"counts={json.dumps(counts, ensure_ascii=False)}")


def _print_apply_summary(apply_result: Any, db_path: Path) -> None:
    _print_stderr(f"APPLIED commercial deal promotion to {db_path}")
    _print_stderr(
        f"deal_key={apply_result.deal_key} deal_id={apply_result.deal_id} "
        f"action={apply_result.deal_action}"
    )
    _print_stderr(f"foreign_key_check_ok={apply_result.foreign_key_check_ok}")
    _print_stderr(f"row_counts={json.dumps(apply_result.row_counts, ensure_ascii=False)}")
    _print_stderr(
        f"inserted={json.dumps(apply_result.inserted, ensure_ascii=False)} "
        f"updated={json.dumps(apply_result.updated, ensure_ascii=False)}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    err = validate_apply_args(
        apply=args.apply,
        sqlite_db=args.sqlite_db,
        deal_key=args.deal_key,
        understand_writes=args.i_understand_this_writes_sqlite,
    )
    if err:
        _print_stderr(f"ERROR: {err}")
        return 2

    deal_key = args.deal_key.strip()
    plan_conn: sqlite3.Connection | None = None
    if args.sqlite_db is not None and not args.apply:
        db_path = args.sqlite_db.expanduser().resolve()
        plan_conn = _optional_ro_conn(db_path)
        if plan_conn is None:
            _print_stderr(
                f"WARN: --sqlite-db not found; idempotency hints assume insert: {db_path}"
            )

    try:
        plan = build_plan_for_deal_key(
            deal_key,
            preview_path=args.preview_json,
            pipeline_root=_ROOT,
            conn=plan_conn,
        )
    except (FileNotFoundError, ValueError) as exc:
        _print_stderr(f"ERROR: {exc}")
        return 1
    finally:
        if plan_conn is not None:
            plan_conn.close()

    report = plan.to_dict()
    json_out_path = args.dry_run_json_out or args.json_out

    if not args.apply:
        if args.summary:
            _print_dry_run_summary(
                plan.deal_key,
                plan.deal_action,
                plan.schema_version,
                plan.counts,
            )
        if json_out_path:
            out_path = json_out_path.expanduser().resolve()
            _write_json_file(out_path, report, pretty=args.pretty_json)
            _print_stderr(f"Wrote {out_path}")
        else:
            sys.stdout.write(_json_text(report, pretty=args.pretty_json))
        return 0

    if json_out_path:
        out_path = json_out_path.expanduser().resolve()
        _write_json_file(out_path, report, pretty=args.pretty_json)
        _print_stderr(f"Wrote plan JSON to {out_path}")

    if args.sqlite_db is None:
        _print_stderr("ERROR: --apply requires --sqlite-db PATH")
        return 2

    db_path = args.sqlite_db.expanduser().resolve()
    path_err = validate_sqlite_apply_target(db_path, allow_production=args.allow_production_sqlite)
    if path_err:
        _print_stderr(f"ERROR: {path_err}")
        return 4

    conn = connect_sqlite_rw(db_path)
    try:
        apply_result = apply_deal_promotion_plan(conn, plan)
    except Exception as exc:
        _print_stderr(f"ERROR: apply failed (rolled back): {exc}")
        return 1
    finally:
        conn.close()

    if args.summary:
        _print_apply_summary(apply_result, db_path)
    else:
        _print_stderr(f"APPLIED commercial deal promotion to {db_path}")
        _print_stderr(
            f"deal_key={apply_result.deal_key} deal_id={apply_result.deal_id} "
            f"action={apply_result.deal_action}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
