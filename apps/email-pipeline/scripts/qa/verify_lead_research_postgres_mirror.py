#!/usr/bin/env python3
"""Verify SQLite lead_research counts match Postgres lead_intel mirror."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from origenlab_email_pipeline.lead_research.lead_research_builder import sqlite_lead_research_counts
from origenlab_email_pipeline.lead_research.lead_research_mirror_safety import (
    FORBIDDEN_MIRROR_KEYS,
    assert_mirror_text_safe,
)
from origenlab_email_pipeline.lead_research.lead_research_postgres_mirror import (
    compare_lead_research_mirror_counts,
    lead_research_mirror_built_counts,
    pg_lead_intel_tables_exist,
    postgres_lead_intel_counts,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import (
    connect_sqlite_readonly,
    resolve_postgres_url,
    resolve_sqlite_path,
)

_TEXT_COLS: dict[str, tuple[str, ...]] = {
    "prospect": (
        "organization_name",
        "contact_name",
        "email",
        "evidence_note",
        "spanish_message_angle",
        "block_or_review_reason",
    ),
    "recommendation": ("suggested_body_preview", "why_this_lead", "safety_note"),
    "evidence": ("evidence_note",),
    "block_reason": ("reason_label",),
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None)
    p.add_argument("--postgres-url", default=None)
    p.add_argument("--scan-text", action="store_true")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args()

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg required", file=sys.stderr)
        return 2

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    pg_url = resolve_postgres_url(args.postgres_url)

    conn = connect_sqlite_readonly(sqlite_path)
    try:
        sqlite_counts_raw = sqlite_lead_research_counts(conn)
        built_counts = lead_research_mirror_built_counts(conn)
    finally:
        conn.close()

    errors: list[str] = []
    pg_counts: dict[str, int] = {}
    with psycopg.connect(pg_url) as pg_conn:
        with pg_conn.cursor() as cur:
            if not pg_lead_intel_tables_exist(cur):
                errors.append("Postgres lead_intel.prospect table missing")
            else:
                pg_counts = postgres_lead_intel_counts(cur)
                errors.extend(compare_lead_research_mirror_counts(built_counts, pg_counts))

                if args.scan_text:
                    for table, cols in _TEXT_COLS.items():
                        for col in cols:
                            cur.execute(
                                f"SELECT {col} FROM lead_intel.{table} WHERE {col} IS NOT NULL"
                            )
                            for (value,) in cur.fetchall():
                                try:
                                    assert_mirror_text_safe(str(value), field=f"lead_intel.{table}.{col}")
                                except ValueError as exc:
                                    errors.append(str(exc))

                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'lead_intel'
                    """
                )
                for (col,) in cur.fetchall():
                    if col in FORBIDDEN_MIRROR_KEYS:
                        errors.append(f"forbidden column present: {col}")

    report = {
        "ok": not errors,
        "errors": errors,
        "sqlite_counts_raw": sqlite_counts_raw,
        "built_counts": built_counts,
        "postgres_counts": pg_counts,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
