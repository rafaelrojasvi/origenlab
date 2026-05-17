#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Promote a confirmed purchase order email into durable SQLite commercial tables.
# Default preset: CEAF OC 26172 (operator-confirmed structured fields).
# Does not send email or modify Gmail.
# -----------------------------------------------------------------------------
"""Promote confirmed purchase order / buyer event into SQLite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.commercial.ceaf_oc_26172 import CEAF_OC_NUMBER
from origenlab_email_pipeline.commercial.commercial_purchase_promotion import (
    INGEST_HINT,
    apply_promotion_plan,
    build_ceaf_oc_26172_plan,
    connect_sqlite_rw,
    plan_to_report_dict,
)
from origenlab_email_pipeline.config import load_settings


def _resolve_db_path(cli_path: Path | None) -> Path:
    if cli_path is not None:
        return cli_path.expanduser().resolve()
    settings = load_settings()
    return settings.sqlite_path.expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Promote a confirmed purchase order email into commercial_purchase_* SQLite tables. "
            "SQLite/Gmail remain authoritative; run dashboard Postgres sync afterward."
        )
    )
    p.add_argument("--sqlite-db", type=Path, default=None, help="Override ORIGENLAB_SQLITE_PATH")
    p.add_argument("--subject", default=None, help="Email subject hint (default: CEAF OC preset)")
    p.add_argument("--oc-number", default=None, help="Purchase order number (default: 26172 for CEAF)")
    p.add_argument("--buyer-domain", default=None, help="Buyer email domain hint (default: ceaf.cl)")
    p.add_argument(
        "--manual-evidence",
        action="store_true",
        help="Break-glass: allow promotion without a linked source email (not implemented for CEAF preset)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print match plan only (default)")
    p.add_argument("--apply", action="store_true", help="Write to SQLite")
    p.add_argument("--json-out", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.manual_evidence:
        print(
            "ERROR: --manual-evidence is not supported for the CEAF preset; ingest the source email first.",
            file=sys.stderr,
        )
        return 2

    db_path = _resolve_db_path(args.sqlite_db)
    if not db_path.is_file():
        print(f"ERROR: SQLite database not found: {db_path}", file=sys.stderr)
        return 2

    oc = (args.oc_number or CEAF_OC_NUMBER).strip()
    if oc != CEAF_OC_NUMBER:
        print(
            f"ERROR: only CEAF OC {CEAF_OC_NUMBER} preset is implemented in this script; got oc-number={oc!r}",
            file=sys.stderr,
        )
        return 2

    conn = connect_sqlite_rw(db_path)
    try:
        plan = build_ceaf_oc_26172_plan(conn)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(INGEST_HINT, file=sys.stderr)
        return 1
    finally:
        conn.close()

    report = plan_to_report_dict(plan)
    report["sqlite_path"] = str(db_path)
    report["dry_run"] = not args.apply

    if args.apply:
        conn = connect_sqlite_rw(db_path)
        try:
            event_id = apply_promotion_plan(conn, plan)
        finally:
            conn.close()
        report["event_id"] = event_id
        report["applied"] = True
    else:
        report["applied"] = False

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to persist.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
