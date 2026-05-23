#!/usr/bin/env python3
"""Read-only verification queries after sync_dashboard_postgres_mirror (Phase 0)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.mart_core_postgres_migrate import resolve_postgres_url  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dashboard Postgres mirror row counts.")
    parser.add_argument("--postgres-url", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg missing — run: uv sync --group dev", file=sys.stderr)
        return 2

    pg_url = resolve_postgres_url(args.postgres_url or os.environ.get("ORIGENLAB_POSTGRES_URL"))
    out: dict[str, object] = {"postgres_url_redacted": pg_url.split("@")[-1] if "@" in pg_url else pg_url}

    queries: dict[str, str] = {
        "schemas": """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name IN (
              'archive','ops','mart','leads','commercial','outbound','supplier','reporting'
            )
            ORDER BY 1
        """,
        "dashboard_sync_run_latest": """
            SELECT id, status, started_at, finished_at, postgres_url_redacted
            FROM reporting.dashboard_sync_run
            ORDER BY id DESC
            LIMIT 1
        """,
        "mart_contact_master": "SELECT COUNT(*)::bigint FROM mart.contact_master",
        "api_v_warm_case": "SELECT COUNT(*)::bigint FROM api.v_warm_case",
        "api_v_equipment_opportunity": "SELECT COUNT(*)::bigint FROM api.v_equipment_opportunity",
        "outbound_outreach_state": "SELECT COUNT(*)::bigint FROM outbound.outreach_contact_state",
        "commercial_warm_case": "SELECT COUNT(*)::bigint FROM commercial.warm_case",
        "equipment_opportunity": "SELECT COUNT(*)::bigint FROM commercial.equipment_opportunity",
        "equipment_source_canonical": """
            SELECT id, is_canonical FROM commercial.equipment_opportunity_source ORDER BY id DESC LIMIT 3
        """,
        "archive_emails": "SELECT COUNT(*)::bigint FROM archive.emails",
    }

    def _table_exists(cur, schema: str, table: str) -> bool:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        )
        return cur.fetchone() is not None

    def _column_exists(cur, schema: str, table: str, column: str) -> bool:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
            """,
            (schema, table, column),
        )
        return cur.fetchone() is not None

    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(queries["schemas"])
            out["schemas_present"] = [r[0] for r in cur.fetchall()]

            for key in (
                "dashboard_sync_run_latest",
                "mart_contact_master",
                "outbound_outreach_state",
                "api_v_warm_case",
                "api_v_equipment_opportunity",
            ):
                cur.execute(queries[key])
                row = cur.fetchone()
                out[key] = row[0] if row and len(row) == 1 else list(row) if row else None

            for optional in ("commercial_warm_case", "equipment_opportunity"):
                try:
                    cur.execute(queries[optional])
                    out[optional] = cur.fetchone()[0]
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    out[optional] = {"error": str(exc)}

            try:
                cur.execute(queries["equipment_source_canonical"])
                out["equipment_source_canonical"] = cur.fetchall()
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                out["equipment_source_canonical"] = {"error": str(exc)}

            if _table_exists(cur, "archive", "emails"):
                cur.execute(queries["archive_emails"])
                out["archive_emails"] = cur.fetchone()[0]
                if _column_exists(cur, "archive", "emails", "body"):
                    cur.execute(
                        """
                        SELECT COUNT(*)::bigint FROM archive.emails
                        WHERE body IS NOT NULL AND length(trim(body)) > 0
                        """
                    )
                    out["archive_emails_with_body"] = cur.fetchone()[0]
                else:
                    out["archive_emails_with_body"] = "column_absent"
            else:
                out["archive_emails"] = None
                out["archive_emails_with_body"] = "schema_absent"

    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
