"""Mirror SQLite commercial_purchase_* tables into Postgres (read-only SQLite)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.commercial_purchase_schema import (
    commercial_purchase_tables_exist,
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

PURCHASE_EVENT_TABLE = ("commercial", "purchase_event")
PURCHASE_EVENT_ITEM_TABLE = ("commercial", "purchase_event_item")
PURCHASE_EVENT_ATTACHMENT_TABLE = ("commercial", "purchase_event_attachment")


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


def _bool_sqlite(v: Any) -> bool:
    return bool(v) if v is not None else False


def load_sqlite_purchase_events(conn: sqlite3.Connection) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if not commercial_purchase_tables_exist(conn):
        return [], [], []

    def _rows(sql: str) -> list[dict[str, Any]]:
        cur = conn.execute(sql)
        cols = [str(d[0]) for d in cur.description or ()]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    events = _rows("SELECT * FROM commercial_purchase_events ORDER BY id")
    items = _rows(
        "SELECT * FROM commercial_purchase_event_items ORDER BY purchase_event_id, line_number"
    )
    attachments = _rows(
        "SELECT * FROM commercial_purchase_event_attachments ORDER BY purchase_event_id, id"
    )
    return events, items, attachments


def sync_commercial_purchase_events(
    pg_url: str,
    sqlite_path: Path,
    *,
    sync_run_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Replace commercial.purchase_* tables from SQLite."""
    _require_psycopg()
    assert psycopg is not None and Json is not None

    ev_schema, ev_table = PURCHASE_EVENT_TABLE
    item_schema, item_table = PURCHASE_EVENT_ITEM_TABLE
    att_schema, att_table = PURCHASE_EVENT_ATTACHMENT_TABLE

    conn = connect_sqlite_readonly(sqlite_path)
    try:
        events, items, attachments = load_sqlite_purchase_events(conn)
    finally:
        conn.close()

    result: dict[str, Any] = {
        "events_built": len(events),
        "items_built": len(items),
        "attachments_built": len(attachments),
        "events_written": 0,
        "items_written": 0,
        "attachments_written": 0,
        "skipped": False,
        "sync_run_id": sync_run_id,
    }
    if dry_run:
        result["skipped"] = True
        return result

    synced_at = datetime.now(timezone.utc)
    with psycopg.connect(pg_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:
            if not pg_table_exists(cur, schema=ev_schema, table=ev_table):
                result["skipped"] = True
                result["reason"] = "table_missing"
                return result

            cur.execute(f"DELETE FROM {att_schema}.{att_table}")
            cur.execute(f"DELETE FROM {item_schema}.{item_table}")
            cur.execute(f"DELETE FROM {ev_schema}.{ev_table}")

            for row in events:
                evidence_raw = row.get("evidence_json") or "{}"
                if isinstance(evidence_raw, str):
                    try:
                        evidence_obj = json.loads(evidence_raw)
                    except json.JSONDecodeError:
                        evidence_obj = {"raw": evidence_raw}
                else:
                    evidence_obj = evidence_raw

                cur.execute(
                    f"""
                    INSERT INTO {ev_schema}.{ev_table} (
                      id, sync_run_id, source_email_id, source_message_id, source_file,
                      email_subject, email_from, email_to, email_date_iso,
                      buyer_org_name, buyer_rut, buyer_contact_name, buyer_contact_role,
                      buyer_contact_email, buyer_domain, purchase_status, oc_number,
                      oc_date, quote_number, quote_date, project_name, project_code,
                      project_responsible, associated_line,
                      net_amount_clp, iva_amount_clp, gross_amount_clp, currency,
                      payment_terms, delivery_address, invoice_email, invoice_cc_email,
                      dispatch_requested, invoice_requested, bank_details_requested,
                      commercial_summary, confidence, evidence_json,
                      created_at, updated_at, synced_at
                    ) VALUES (
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s, %s,
                      %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s
                    )
                    """,
                    (
                        row["id"],
                        sync_run_id,
                        row.get("source_email_id"),
                        row.get("source_message_id"),
                        row.get("source_file"),
                        row.get("email_subject"),
                        row.get("email_from"),
                        row.get("email_to"),
                        row.get("email_date_iso"),
                        row["buyer_org_name"],
                        row.get("buyer_rut"),
                        row.get("buyer_contact_name"),
                        row.get("buyer_contact_role"),
                        row.get("buyer_contact_email"),
                        row.get("buyer_domain"),
                        row["purchase_status"],
                        row["oc_number"],
                        row.get("oc_date"),
                        row.get("quote_number"),
                        row.get("quote_date"),
                        row.get("project_name"),
                        row.get("project_code"),
                        row.get("project_responsible"),
                        row.get("associated_line"),
                        row.get("net_amount_clp"),
                        row.get("iva_amount_clp"),
                        row.get("gross_amount_clp"),
                        row.get("currency") or "CLP",
                        row.get("payment_terms"),
                        row.get("delivery_address"),
                        row.get("invoice_email"),
                        row.get("invoice_cc_email"),
                        _bool_sqlite(row.get("dispatch_requested")),
                        _bool_sqlite(row.get("invoice_requested")),
                        _bool_sqlite(row.get("bank_details_requested")),
                        row.get("commercial_summary"),
                        row.get("confidence") or "operator_confirmed",
                        Json(evidence_obj),
                        row.get("created_at"),
                        row.get("updated_at"),
                        synced_at,
                    ),
                )

            for row in items:
                cur.execute(
                    f"""
                    INSERT INTO {item_schema}.{item_table} (
                      id, purchase_event_id, line_number, ref_code, product_name,
                      brand, quantity, net_amount_clp, evidence_source, created_at, synced_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["id"],
                        row["purchase_event_id"],
                        row["line_number"],
                        row.get("ref_code"),
                        row["product_name"],
                        row.get("brand"),
                        row.get("quantity"),
                        row.get("net_amount_clp"),
                        row.get("evidence_source"),
                        row.get("created_at"),
                        synced_at,
                    ),
                )

            for row in attachments:
                amounts_raw = row.get("extracted_amounts_json")
                amounts_json = None
                if amounts_raw:
                    try:
                        amounts_json = Json(json.loads(amounts_raw))
                    except (json.JSONDecodeError, TypeError):
                        amounts_json = Json({"raw": str(amounts_raw)})

                cur.execute(
                    f"""
                    INSERT INTO {att_schema}.{att_table} (
                      id, purchase_event_id, source_attachment_id, filename, mime_type,
                      document_type, extracted_text_present, extracted_amounts_json,
                      created_at, synced_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["id"],
                        row["purchase_event_id"],
                        row.get("source_attachment_id"),
                        row["filename"],
                        row.get("mime_type"),
                        row.get("document_type"),
                        _bool_sqlite(row.get("extracted_text_present")),
                        amounts_json,
                        row.get("created_at"),
                        synced_at,
                    ),
                )

        pg_conn.commit()

    result["events_written"] = len(events)
    result["items_written"] = len(items)
    result["attachments_written"] = len(attachments)
    return result
