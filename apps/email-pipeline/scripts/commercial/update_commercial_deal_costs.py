#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Add operator-confirmed CLP margin costs and compute deal margin when complete.
# Default: dry-run JSON plan. --apply writes to --sqlite-db (backup/dev paths only).
# -----------------------------------------------------------------------------
"""Update commercial deal margin costs and compute margin when all required costs are set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.commercial.commercial_deal_inspector import connect_readonly  # noqa: E402
from origenlab_email_pipeline.commercial.commercial_deal_margin import (  # noqa: E402
    MarginCostInputs,
    apply_margin_update_plan,
    build_margin_update_plan,
    validate_apply_args,
)
from origenlab_email_pipeline.commercial.commercial_deal_promotion import (  # noqa: E402
    connect_sqlite_rw,
    validate_sqlite_apply_target,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, required=True)
    p.add_argument("--deal-key", required=True)
    p.add_argument("--wise-clp-debit", type=int, default=None, help="Wise card CLP debit")
    p.add_argument("--dhl-cost-clp", type=int, default=None, help="DHL / logistics CLP")
    p.add_argument("--import-cost-clp", type=int, default=None, help="Import / customs CLP")
    p.add_argument("--bank-fee-clp", type=int, default=None, help="Optional bank fee CLP")
    p.add_argument("--note", default=None, help="Operator note (required when setting a cost to 0)")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--i-understand-this-writes-sqlite", action="store_true")
    p.add_argument("--summary", action="store_true", help="Human summary on stderr")
    p.add_argument(
        "--pretty-json",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p.add_argument("--allow-production-sqlite", action="store_true", help=argparse.SUPPRESS)
    return p


def _inputs_from_args(args: argparse.Namespace) -> MarginCostInputs:
    return MarginCostInputs(
        wise_clp_debit=args.wise_clp_debit,
        dhl_cost_clp=args.dhl_cost_clp,
        import_cost_clp=args.import_cost_clp,
        bank_fee_clp=args.bank_fee_clp,
        note=args.note,
    )


def _print_summary(plan_dict: dict[str, Any], *, applied: bool) -> None:
    prefix = "APPLIED" if applied else "DRY-RUN"
    print(f"{prefix} margin update for {plan_dict['deal_key']}", file=sys.stderr)
    print(f"margin_status={plan_dict.get('margin_status')}", file=sys.stderr)
    if plan_dict.get("margin_net_clp") is not None:
        print(
            f"margin_net_clp={plan_dict['margin_net_clp']} margin_pct={plan_dict.get('margin_pct')}",
            file=sys.stderr,
        )
    if plan_dict.get("remaining_blockers"):
        print(f"remaining_blockers={plan_dict['remaining_blockers']}", file=sys.stderr)
    if plan_dict.get("cost_actions"):
        print(f"cost_actions={plan_dict['cost_actions']}", file=sys.stderr)


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

    inputs = _inputs_from_args(args)
    if not inputs.provided_slots() and not args.apply:
        print(
            "WARN: no cost flags provided; plan reflects existing DB costs only",
            file=sys.stderr,
        )

    db_path = args.sqlite_db.expanduser().resolve()
    deal_key = args.deal_key.strip()

    try:
        if args.apply:
            path_err = validate_sqlite_apply_target(
                db_path, allow_production=args.allow_production_sqlite
            )
            if path_err:
                print(f"ERROR: {path_err}", file=sys.stderr)
                return 4
            conn = connect_sqlite_rw(db_path)
            try:
                plan = build_margin_update_plan(conn, deal_key, inputs, mode="apply")
                result = apply_margin_update_plan(conn, plan)
            finally:
                conn.close()
            payload = {**plan.to_dict(), "applied": True, "cost_actions": result.get("cost_actions")}
            if args.summary:
                _print_summary({**plan.to_dict(), **result}, applied=True)
        else:
            conn = connect_readonly(db_path)
            try:
                plan = build_margin_update_plan(conn, deal_key, inputs, mode="dry_run")
            finally:
                conn.close()
            payload = plan.to_dict()
            if args.summary:
                _print_summary(payload, applied=False)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    indent = 2 if args.pretty_json else None
    sys.stdout.write(json.dumps(payload, indent=indent, ensure_ascii=False, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
