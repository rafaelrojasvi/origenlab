#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# EXPERIMENTAL_PARKED: Promote SQLite warm review queue into Postgres warm_case tables.
# Read-only SQLite; writes commercial.warm_case* only. Default dry-run.
# Does not mutate Gmail.
# -----------------------------------------------------------------------------
"""Promote warm cases from SQLite cases_review_queue into Postgres (DB-2B)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings  # noqa: E402
from origenlab_email_pipeline.warm_case_promotion import (  # noqa: E402
    apply_promotion,
    preview_promotion,
)


def _resolve_sqlite_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = (os.environ.get("ORIGENLAB_SQLITE_PATH") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return load_settings().resolved_sqlite_path()


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


def _optional_postgres_url(explicit: str | None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    return (os.environ.get("ALEMBIC_DATABASE_URL") or "").strip() or None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Promote SQLite cases_review_queue rows into Postgres commercial.warm_case*. "
            "Dry-run by default; --apply writes to Postgres."
        )
    )
    p.add_argument("--sqlite-db", type=Path, default=None, help="SQLite path (default: ORIGENLAB_SQLITE_PATH)")
    p.add_argument("--postgres-url", default=None, help="Postgres URL for --apply (else ALEMBIC_DATABASE_URL)")
    p.add_argument("--days-window", type=int, default=30, help="Queue lookback days (default: 30)")
    p.add_argument("--limit", type=int, default=200, help="Max queue rows to scan (default: 200)")
    p.add_argument(
        "--include-noise",
        action="store_true",
        help="Include obvious noise rows from queue (default: exclude noise)",
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sqlite_path = _resolve_sqlite_path(args.sqlite_db)
    if not sqlite_path.is_file():
        print(f"ERROR: SQLite database not found: {sqlite_path}", file=sys.stderr)
        return 2

    exclude_noise = not args.include_noise

    try:
        if args.apply:
            if not (args.updated_by and str(args.updated_by).strip()):
                print("ERROR: --apply requires --updated-by (or --operator)", file=sys.stderr)
                return 2
            if not (args.reason and str(args.reason).strip()):
                print("ERROR: --apply requires --reason", file=sys.stderr)
                return 2
            summary = apply_promotion(
                _resolve_postgres_url(args.postgres_url),
                sqlite_path,
                days_window=args.days_window,
                exclude_obvious_noise=exclude_noise,
                limit=args.limit,
                updated_by=str(args.updated_by).strip(),
                reason=str(args.reason).strip(),
            )
        else:
            summary = preview_promotion(
                sqlite_path,
                days_window=args.days_window,
                exclude_obvious_noise=exclude_noise,
                limit=args.limit,
                pg_url=_optional_postgres_url(args.postgres_url),
            )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
