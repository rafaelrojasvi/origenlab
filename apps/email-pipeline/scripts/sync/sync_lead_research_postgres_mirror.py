#!/usr/bin/env python3
"""Sync SQLite lead_research_* → Postgres lead_intel.* (redacted read mirror)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from origenlab_email_pipeline.lead_research.lead_research_postgres_mirror import (  # noqa: E402
    sync_lead_research_postgres_mirror,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import (  # noqa: E402
    resolve_postgres_url,
    resolve_sqlite_path,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None)
    p.add_argument("--postgres-url", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args()

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    pg_url = resolve_postgres_url(args.postgres_url)

    result = sync_lead_research_postgres_mirror(pg_url, sqlite_path, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result.get("reason") == "table_missing":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
