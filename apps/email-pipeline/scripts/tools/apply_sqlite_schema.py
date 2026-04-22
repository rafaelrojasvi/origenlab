#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY: Mutates SQLite schema (DDL / additive migrations) on the target DB file.
# Run against the correct ORIGENLAB_SQLITE_PATH; keep backups before first use on prod.
# See docs/SCRIPT_MAP.md — "Break-glass scripts" for other high-impact tools.
# -----------------------------------------------------------------------------
"""Apply orchestrated SQLite DDL (additive migrations) and run PRAGMA checks.

This does **not** rebuild ``contact_master`` / marts (use ``scripts/mart/build_business_mart.py`` for that).
It is safe to run on your working ``emails.sqlite`` to pick up new tables/columns — same layers as
``migrate_sqlite_schema(conn)`` with no arguments. Use ``--commercial-intel`` if you use that stack.

Example::

  uv run python scripts/tools/apply_sqlite_schema.py
  uv run python scripts/tools/apply_sqlite_schema.py ~/data/origenlab-email/sqlite/emails.sqlite --commercial-intel

  # Large DB: DDL only (avoid slow PRAGMA integrity_check):
  uv run python scripts/tools/apply_sqlite_schema.py --migrate-only
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply migrate_sqlite_schema + SQLite integrity checks.")
    ap.add_argument(
        "db",
        nargs="?",
        type=Path,
        default=None,
        help="SQLite path (default: from config)",
    )
    ap.add_argument(
        "--commercial-intel",
        action="store_true",
        help="Also apply COMMERCIAL_INTEL layer (off by default; matches bare migrate unless you need it).",
    )
    ap.add_argument(
        "--migrate-only",
        action="store_true",
        help="Skip PRAGMA integrity/quick/foreign_key checks (full integrity_check can take minutes on huge DBs).",
    )
    args = ap.parse_args()
    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("Database file not found:", db_path, file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path), timeout=120.0)
    try:
        if args.commercial_intel:
            migrate_sqlite_schema(
                conn,
                layers={
                    SchemaLayer.ARCHIVE_AND_MART,
                    SchemaLayer.COMMERCIAL_INTEL,
                    SchemaLayer.LEADS,
                    SchemaLayer.LEAD_ACCOUNTS,
                    SchemaLayer.SUPPLIERS,
                },
            )
            print(
                "Applied layers: ARCHIVE_AND_MART, COMMERCIAL_INTEL, LEADS, LEAD_ACCOUNTS, SUPPLIERS",
            )
        else:
            migrate_sqlite_schema(conn)
            print("Applied default migrate_sqlite_schema(conn) layers (no COMMERCIAL_INTEL).")
        conn.commit()
        if args.migrate_only:
            print("Skipped PRAGMA checks (--migrate-only).")
            return 0
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()

    print("PRAGMA integrity_check:", integrity)
    print("PRAGMA quick_check:", quick)
    if fk:
        print("PRAGMA foreign_key_check: FAILED", len(fk), "row(s)", file=sys.stderr)
        for row in fk[:20]:
            print(" ", row, file=sys.stderr)
        return 2
    print("PRAGMA foreign_key_check: ok (0 rows)")
    if integrity.lower() != "ok" or str(quick).lower() != "ok":
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
