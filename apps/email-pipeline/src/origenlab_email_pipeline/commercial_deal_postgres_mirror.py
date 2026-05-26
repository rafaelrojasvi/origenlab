"""Mirror SQLite commercial_deal ledger into Postgres commercial.deal (read-only, redacted)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.commercial_deal_mirror_read_model import (
    load_all_safe_deal_mirror_rows,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import connect_sqlite_readonly

try:
    import psycopg
    from psycopg.types.json import Json
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    Json = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

COMMERCIAL_DEAL_TABLE = ("commercial", "deal")


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            f"psycopg is required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


def pg_table_exists(cur: Any, *, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def sync_commercial_deals(
    pg_url: str,
    sqlite_path: Path,
    *,
    sync_run_id: int | None = None,
    dry_run: bool = False,
    deal_key_filter: str | None = None,
) -> dict[str, Any]:
    """Replace commercial.deal from SQLite with redacted read-model rows."""
    _require_psycopg()
    assert psycopg is not None and Json is not None

    schema, table = COMMERCIAL_DEAL_TABLE
    conn = connect_sqlite_readonly(sqlite_path)
    try:
        rows = load_all_safe_deal_mirror_rows(conn, deal_key_filter=deal_key_filter)
    finally:
        conn.close()

    result: dict[str, Any] = {
        "deals_built": len(rows),
        "deals_written": 0,
        "skipped": False,
        "sync_run_id": sync_run_id,
    }
    if dry_run:
        result["skipped"] = True
        return result

    synced_at = datetime.now(timezone.utc)
    with psycopg.connect(pg_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:
            if not pg_table_exists(cur, schema=schema, table=table):
                result["skipped"] = True
                result["reason"] = "table_missing"
                return result

            cur.execute(f"DELETE FROM {schema}.{table}")

            for row in rows:
                cur.execute(
                    f"""
                    INSERT INTO {schema}.{table} (
                      deal_key, sync_run_id,
                      client_org_name, supplier_org_name,
                      deal_status, margin_status, reconciliation_status, freight_status,
                      client_sale_net_clp, client_iva_amount_clp,
                      client_sale_gross_clp, client_payment_received_clp,
                      supplier_invoice_total_decimal, supplier_invoice_total_minor,
                      supplier_amount_paid_decimal, supplier_amount_paid_minor,
                      margin_net_clp, margin_pct, updated_at,
                      product_line_summaries, cost_summaries_by_type,
                      payment_summaries_masked, margin_blockers,
                      synced_at
                    ) VALUES (
                      %s, %s,
                      %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s, %s,
                      %s
                    )
                    """,
                    (
                        row["deal_key"],
                        sync_run_id,
                        row["client_org_name"],
                        row["supplier_org_name"],
                        row["deal_status"],
                        row["margin_status"],
                        row.get("reconciliation_status"),
                        row.get("freight_status"),
                        row.get("client_sale_net_clp"),
                        row.get("client_iva_amount_clp"),
                        row.get("client_sale_gross_clp"),
                        row.get("client_payment_received_clp"),
                        row.get("supplier_invoice_total_decimal"),
                        row.get("supplier_invoice_total_minor"),
                        row.get("supplier_amount_paid_decimal"),
                        row.get("supplier_amount_paid_minor"),
                        row.get("margin_net_clp"),
                        row.get("margin_pct"),
                        row.get("updated_at"),
                        Json(row.get("product_line_summaries") or []),
                        Json(row.get("cost_summaries_by_type") or []),
                        Json(row.get("payment_summaries_masked") or []),
                        Json(row.get("margin_blockers") or []),
                        synced_at,
                    ),
                )

            result["deals_written"] = len(rows)
        pg_conn.commit()

    return result
