#!/usr/bin/env python3
"""Match lead_master to organization_master and contact_master; write match tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.leads_match import match_leads_to_mart
from origenlab_email_pipeline.pipeline_run_recorder import finish_run, set_kv, start_run
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def main() -> int:
    ap = argparse.ArgumentParser(description="Match leads to existing mart orgs and contacts")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    migrate_sqlite_schema(conn, layers={SchemaLayer.LEADS})
    run_id = start_run(
        conn,
        script_name="scripts/leads/match_leads_to_mart.py",
        notes="lead vs mart org and contact matching",
    )
    try:
        org_n, contact_n = match_leads_to_mart(conn, pipeline_run_id=run_id)
        set_kv(conn, "last_lead_match_run_id", str(run_id))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        finish_run(conn, run_id)
        conn.close()
    print(
        f"Wrote {org_n} org match rows (lead_matches_existing_orgs), "
        f"{contact_n} contact match rows (lead_matches_existing_contacts)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
