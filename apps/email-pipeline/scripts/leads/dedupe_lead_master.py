#!/usr/bin/env python3
"""Merge duplicate lead_master rows sharing (source_name, canonical source_record_id).

Repoints enrichment, mart matches, and lead_account_membership; recreates the unique index.

Dry-run (default): print duplicate groups only; no database writes.

Apply::

    uv run python scripts/leads/dedupe_lead_master.py --apply

After a failed migrate due to duplicates, run --apply once, then re-run normalize / ensure schema.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_master_dedupe import apply_lead_master_dedupe
from origenlab_email_pipeline.lead_master_keys import list_duplicate_key_groups
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Perform merge (default is dry-run listing only)",
    )
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_master'"
        ).fetchone():
            print("No lead_master table.", file=sys.stderr)
            return 0
        if not args.apply:
            ensure_leads_tables_ddl_base(conn)
            groups = list_duplicate_key_groups(conn)
            if not groups:
                print("No duplicate key groups (dry-run).")
                return 0
            print(f"Dry-run: would merge {len(groups)} group(s):", file=sys.stderr)
            for sn, sk, ids in groups:
                print(f"  source_name={sn!r} canonical_id={sk!r} lead_ids={ids}")
            print("Re-run with --apply to execute.", file=sys.stderr)
            return 0
        stats = apply_lead_master_dedupe(conn)
        print(
            f"Dedupe complete: groups_merged={stats.groups_merged} "
            f"leads_deleted={stats.leads_deleted} "
            f"enrichment_repointed={stats.enrichment_repointed} "
            f"enrichment_dropped={stats.enrichment_dropped}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
