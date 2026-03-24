#!/usr/bin/env python3
"""Normalize external_leads_raw into lead_master. Optionally ensure schema only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_master_keys import canonical_source_record_id
from origenlab_email_pipeline.lead_normalize_upsert import upsert_lead_master_row
from origenlab_email_pipeline.leads_normalize import raw_to_normalized
from origenlab_email_pipeline.leads_schema import ensure_leads_tables


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize raw leads into lead_master")
    ap.add_argument("--ensure-schema-only", action="store_true", help="Only create lead tables and exit")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    # Long-running upserts benefit from a busy timeout under WAL mode.
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_leads_tables(conn)
    if args.ensure_schema_only:
        conn.close()
        print("Lead tables ensured.")
        return 0
    rows = conn.execute("SELECT source_name, source_record_id, raw_json FROM external_leads_raw").fetchall()
    n = 0
    batch = 0
    for source_name, source_record_id, raw_json in rows:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or {})
        except (json.JSONDecodeError, TypeError):
            raw = {}
        if not isinstance(raw, dict):
            continue
        try:
            normalized = raw_to_normalized(source_name, raw)
        except Exception as e:
            print(f"Warning: skip raw {source_name}/{source_record_id}: {e}", file=sys.stderr)
            continue
        normalized["source_record_id"] = canonical_source_record_id(source_record_id)
        upsert_lead_master_row(conn, normalized)
        n += 1
        batch += 1
        # Commit periodically so results are visible and to reduce long transactions.
        if batch >= 2000:
            conn.commit()
            batch = 0
            if n % 10000 == 0:
                print(f"…normalized {n}/{len(rows)}", file=sys.stderr)
    conn.commit()
    conn.close()
    print(f"Normalized {n} leads into lead_master.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
