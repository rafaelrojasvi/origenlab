#!/usr/bin/env python3
"""Sync redacted product catalogue from SQLite catalog_* to Postgres catalog.*.

SAFETY: Read-only SQLite. Writes Postgres mirror tables only. Opt-in — not run by default.
Requires: alembic upgrade head (revision 20260527_0019+).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.catalog.catalog_postgres_mirror import (  # noqa: E402
    sync_catalog_postgres_mirror,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import (  # noqa: E402
    resolve_postgres_url,
    resolve_sqlite_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-db", type=Path, default=None)
    parser.add_argument("--postgres-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    pg_url = resolve_postgres_url(args.postgres_url)

    result = sync_catalog_postgres_mirror(pg_url, sqlite_path, dry_run=bool(args.dry_run))
    text = json.dumps(result, indent=2, default=str)
    print(text)

    if not result.get("dry_run") and not result.get("skipped"):
        written = result.get("written_counts") or {}
        for table, count in sorted(written.items()):
            print(f"  {table}: {count}")

    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.json_out}")

    if result.get("reason") == "table_missing":
        print(
            "ERROR: catalog.product missing — run: uv run alembic upgrade head",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
