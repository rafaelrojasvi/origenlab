#!/usr/bin/env python3
"""Merge Presentación OrigenLab CSVs into lead_research_prospect (read-only SQLite ingest)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from origenlab_email_pipeline.lead_research.lead_research_schema import (
    ensure_lead_research_origin_columns,
    ensure_lead_research_tables,
)
from origenlab_email_pipeline.lead_research.presentacion_prospectos_merge import (
    merge_presentacion_into_lead_research,
)
from origenlab_email_pipeline.config import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="Operational SQLite path (default: from settings)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory with presentacion_batch*.csv (default: reports/out/active/current)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = args.out_dir or (repo_root / "reports" / "out" / "active" / "current")
    sqlite_path = args.sqlite or Path(settings.sqlite_path)
    conn = sqlite3.connect(sqlite_path)
    try:
        ensure_lead_research_tables(conn)
        ensure_lead_research_origin_columns(conn)
        result = merge_presentacion_into_lead_research(conn, out_dir, dry_run=args.dry_run)
    finally:
        conn.close()

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
