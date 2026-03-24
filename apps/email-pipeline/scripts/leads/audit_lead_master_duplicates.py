#!/usr/bin/env python3
"""Read-only audit: lead_master source keys (duplicates + weak identity signals).

Reports duplicate (source_name, canonical source_record_id) groups, blank canonical IDs,
per-source totals, and small samples. Non-destructive.

Canonical key (DB-aligned): COALESCE(NULLIF(TRIM(source_record_id), ''), '').

Usage::

    uv run python scripts/leads/audit_lead_master_duplicates.py
    uv run python scripts/leads/audit_lead_master_duplicates.py --db "$ORIGENLAB_SQLITE_PATH"
    uv run python scripts/leads/audit_lead_master_duplicates.py --fail-on-duplicates   # CI: exit 1 if dup groups

``--db`` must be an **existing** file. This script opens SQLite read-only and does not create parent
directories (unlike ingest helpers), so placeholder paths will fail fast with a clear error.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.lead_master_audit import (
    collect_lead_master_identity_audit,
    format_audit_report_lines,
)


def _connect_audit_readonly(resolved_db: Path) -> sqlite3.Connection:
    """Open DB read-only; require file to exist (no mkdir)."""
    if not resolved_db.is_file():
        raise FileNotFoundError(
            f"SQLite database not found: {resolved_db}\n"
            "Use a real path for --db or set ORIGENLAB_SQLITE_PATH. "
            "Audit does not create directories."
        )
    uri = f"{resolved_db.as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=60.0)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--fail-on-duplicates",
        action="store_true",
        help="Exit 1 only if any duplicate key groups exist (unchanged semantics)",
    )
    ap.add_argument(
        "--sample-limit",
        type=int,
        default=4,
        help="Max sample rows per section per source (default: 4, cap 20 in module)",
    )
    args = ap.parse_args()
    settings = load_settings()
    db_path = (args.db or settings.resolved_sqlite_path()).expanduser().resolve()
    try:
        conn = _connect_audit_readonly(db_path)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_master'"
        ).fetchone():
            print("No lead_master table (nothing to audit).")
            return 0
        audit = collect_lead_master_identity_audit(conn, db_path)
        lines = format_audit_report_lines(
            audit,
            sample_limit=args.sample_limit,
            conn=conn,
        )
        print("\n".join(lines))
        if args.fail_on_duplicates and audit.global_duplicate_groups > 0:
            print(
                "\n--fail-on-duplicates: exiting 1 "
                f"({audit.global_duplicate_groups} duplicate key group(s)).",
                file=sys.stderr,
            )
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
