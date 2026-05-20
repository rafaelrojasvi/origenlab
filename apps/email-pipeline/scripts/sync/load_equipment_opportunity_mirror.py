#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# EXPERIMENTAL_PARKED: Postgres mirror loader for equipment-first operator queue.
# Read-only CSV + manifest; writes commercial.equipment_opportunity* only.
# Default dry-run. Does not mutate Gmail or SQLite.
# -----------------------------------------------------------------------------
"""Load canonical equipment_first_operator_queue CSV into Postgres (DB-2A)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.equipment_opportunity_mirror import (  # noqa: E402
    apply_load,
    preview_load,
)


def _default_active_current() -> Path:
    return (_ROOT / "reports" / "out" / "active" / "current").resolve()


def _resolve_postgres_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("ALEMBIC_DATABASE_URL") or "").strip()
    if env:
        return env
    raise RuntimeError(
        "Postgres URL required for --apply: pass --postgres-url or set ALEMBIC_DATABASE_URL "
        "(ORIGENLAB_POSTGRES_URL is not used by this loader)."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Mirror equipment_first_operator_queue_*.csv into Postgres commercial tables. "
            "Dry-run by default; --apply writes to Postgres."
        )
    )
    p.add_argument(
        "--active-current",
        type=Path,
        default=None,
        help="active/current directory (default: reports/out/active/current)",
    )
    p.add_argument(
        "--csv-path",
        type=Path,
        default=None,
        help="Override queue CSV path (must not be buyer_opportunity_crosscheck)",
    )
    p.add_argument(
        "--postgres-url",
        default=None,
        help="Postgres URL for --apply (else ALEMBIC_DATABASE_URL)",
    )
    p.add_argument("--apply", action="store_true", help="Write to Postgres (default: dry-run)")
    p.add_argument(
        "--updated-by",
        "--operator",
        dest="updated_by",
        default=None,
        help="Operator id for apply audit (required with --apply)",
    )
    p.add_argument("--reason", default=None, help="Reason for apply (required with --apply)")
    p.add_argument("--sync-run-id", type=int, default=None, help="Optional reporting.dashboard_sync_run id")
    p.add_argument(
        "--replace-source",
        action="store_true",
        help="Reload rows for an existing source with the same csv_path (scoped delete + insert)",
    )
    return p


def _optional_postgres_url(explicit: str | None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    return (os.environ.get("ALEMBIC_DATABASE_URL") or "").strip() or None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    active_current = (args.active_current or _default_active_current()).expanduser().resolve()

    try:
        if args.apply:
            if not (args.updated_by and str(args.updated_by).strip()):
                print("ERROR: --apply requires --updated-by (or --operator)", file=sys.stderr)
                return 2
            if not (args.reason and str(args.reason).strip()):
                print("ERROR: --apply requires --reason", file=sys.stderr)
                return 2
            pg_url = _resolve_postgres_url(args.postgres_url)
            summary = apply_load(
                pg_url,
                active_current,
                csv_path=args.csv_path,
                updated_by=str(args.updated_by).strip(),
                reason=str(args.reason).strip(),
                sync_run_id=args.sync_run_id,
                replace_source=args.replace_source,
            )
        else:
            summary = preview_load(
                active_current,
                csv_path=args.csv_path,
                pg_url=_optional_postgres_url(args.postgres_url),
                replace_source=args.replace_source,
            )
    except FileNotFoundError as exc:
        summary = {"dry_run": not args.apply, "applied": False, "error": str(exc)}
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2, default=str))
    if summary.get("duplicate_codigos") and args.apply:
        return 1
    if summary.get("error") == "duplicate_codigo_licitacion_in_csv":
        return 1
    if summary.get("error") == "source_already_loaded":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
