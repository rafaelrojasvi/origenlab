#!/usr/bin/env python3
"""Sync redacted commercial deal ledger from SQLite to Postgres commercial.deal.

SAFETY: Read-only SQLite. Writes Postgres mirror table only. Opt-in — not run by default.
Requires: alembic upgrade head (revision 20260526_0018+).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.commercial_deal_postgres_mirror import (  # noqa: E402
    sync_commercial_deals,
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
    parser.add_argument("--deal-key", default=None, help="Sync single deal only")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    pg_url = resolve_postgres_url(args.postgres_url)

    result = sync_commercial_deals(
        pg_url,
        sqlite_path,
        dry_run=bool(args.dry_run),
        deal_key_filter=args.deal_key,
    )
    text = json.dumps(result, indent=2, default=str)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("skipped") or result.get("deals_written", 0) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
