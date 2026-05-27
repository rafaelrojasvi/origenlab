#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Phase 8B: build local SQLite product catalogue from catalog_seed_v1.json.
# SQLite only — no Postgres, API, or dashboard.
# -----------------------------------------------------------------------------
"""Build operator product catalogue tables in SQLite."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.catalog.catalog_builder import (  # noqa: E402
    build_catalog_from_seed_file,
)
from origenlab_email_pipeline.catalog.catalog_schema import (  # noqa: E402
    CATALOG_SCHEMA_VERSION,
    CATALOG_TABLE_NAMES,
    catalog_tables_exist,
    foreign_key_check_ok,
)
from origenlab_email_pipeline.catalog.catalog_seed import (  # noqa: E402
    CATALOG_SEED_VERSION,
    default_seed_path,
)


def _default_sqlite_db() -> Path:
    env = os.environ.get("ORIGENLAB_SQLITE_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "data" / "origenlab-email" / "sqlite" / "emails.sqlite"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sqlite-db",
        type=Path,
        default=None,
        help="SQLite database path (default: ORIGENLAB_SQLITE_PATH or ~/data/.../emails.sqlite)",
    )
    p.add_argument(
        "--seed",
        type=Path,
        default=None,
        help="Seed JSON path (default: data/catalog/catalog_seed_v1.json)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate seed and report counts without writing",
    )
    p.add_argument("--json-out", type=Path, default=None, help="Write summary JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    seed_path = (args.seed or default_seed_path(_ROOT)).expanduser().resolve()
    if not seed_path.is_file():
        print(f"ERROR: seed file not found: {seed_path}", file=sys.stderr)
        return 2

    if args.dry_run:
        conn = sqlite3.connect(":memory:")
        try:
            summary = build_catalog_from_seed_file(conn, seed_path, dry_run=True)
        finally:
            conn.close()
        print(f"DRY-RUN catalog seed {CATALOG_SEED_VERSION} (no file modified)")
        print(f"seed: {seed_path}")
    else:
        db_path = (args.sqlite_db or _default_sqlite_db()).expanduser().resolve()
        if not db_path.parent.is_dir():
            print(f"ERROR: parent directory missing: {db_path.parent}", file=sys.stderr)
            return 2
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            summary = build_catalog_from_seed_file(conn, seed_path, dry_run=False)
            if not foreign_key_check_ok(conn):
                print("ERROR: foreign_key_check failed after build", file=sys.stderr)
                return 1
        finally:
            conn.close()
        print(f"APPLIED catalog schema {CATALOG_SCHEMA_VERSION} to {db_path}")
        print(f"seed: {seed_path}")

    report = summary.as_dict()
    report["catalog_schema_version"] = CATALOG_SCHEMA_VERSION
    report["seed_version"] = CATALOG_SEED_VERSION
    report["tables"] = list(CATALOG_TABLE_NAMES)

    for key in (
        "products",
        "aliases",
        "categories",
        "category_maps",
        "specs",
        "supplier_offers",
        "price_snapshots",
        "commercial_links",
    ):
        print(f"  {key}: {report[key]}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
