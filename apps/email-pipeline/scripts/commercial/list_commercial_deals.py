#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# List commercial deals from local SQLite — read-only.
# -----------------------------------------------------------------------------
"""List commercial deals from SQLite without manual SQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.commercial.commercial_deal_inspector import connect_readonly  # noqa: E402
from origenlab_email_pipeline.commercial.commercial_deal_list import (  # noqa: E402
    DealListFilters,
    deal_list_to_json_payload,
    fetch_deal_list,
    format_deal_list_human,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, required=True, help="SQLite path (read-only)")
    p.add_argument("--status", default=None, help="Filter by deal_status")
    p.add_argument("--margin-status", default=None, help="Filter by margin_status")
    p.add_argument("--client", default=None, help="Filter client org/domain (substring)")
    p.add_argument("--supplier", default=None, help="Filter supplier org/domain (substring)")
    p.add_argument(
        "--needs-margin-review",
        action="store_true",
        help="Only deals with margin_status=needs_review",
    )
    p.add_argument("--limit", type=int, default=None, help="Max rows to return")
    p.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    p.add_argument(
        "--pretty-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-print JSON (default: on)",
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

    filters = DealListFilters(
        status=args.status,
        margin_status=args.margin_status,
        client=args.client,
        supplier=args.supplier,
        needs_margin_review=args.needs_margin_review,
        limit=args.limit,
    )
    try:
        deals = fetch_deal_list(conn, filters)
    finally:
        conn.close()

    if args.output_json:
        payload = deal_list_to_json_payload(deals)
        indent = 2 if args.pretty_json else None
        sys.stdout.write(
            json.dumps(payload, indent=indent, ensure_ascii=False, default=str) + "\n"
        )
    else:
        print(format_deal_list_human(deals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
