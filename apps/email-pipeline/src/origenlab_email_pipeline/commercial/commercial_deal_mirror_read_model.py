"""Build redacted commercial deal rows for Postgres dashboard mirror (read-only)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from origenlab_email_pipeline.commercial.commercial_deal_margin import (
    margin_blockers_for_deal,
    margin_pct_from_notes,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    commercial_deal_tables_exist,
)

# Keys that must never appear in mirror JSON payloads.
FORBIDDEN_MIRROR_JSON_KEYS: frozenset[str] = frozenset(
    {
        "transfer_id",
        "operation_id",
        "source_preview_path",
        "source_preview_sha256",
        "notes_json",
        "operator_private_json",
        "legacy_purchase_event_id",
        "source_path",
        "source_file",
        "source_email_id",
        "source_attachment_id",
        "extract_snippet",
        "operator_note",
        "client_contact_email",
        "supplier_contact_email",
        "client_domain",
        "supplier_domain",
        "margin_notes",
        "gmail_url",
        "body",
        "full_text",
        "email_body",
    }
)

FORBIDDEN_KEY_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "body",
        "full_body",
        "attachment_extract",
        "full_text",
        "gmail",
    }
)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row)))


def _is_forbidden_key(key: str) -> bool:
    if key in FORBIDDEN_MIRROR_JSON_KEYS:
        return True
    lower = key.lower()
    return any(sub in lower for sub in FORBIDDEN_KEY_SUBSTRINGS)


def assert_mirror_payload_safe(payload: Any, *, path: str = "") -> None:
    """Raise ValueError if a forbidden key appears anywhere in a mirror JSON tree."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _is_forbidden_key(str(key)):
                raise ValueError(f"forbidden mirror key at {path}.{key}")
            assert_mirror_payload_safe(value, path=f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_mirror_payload_safe(item, path=f"{path}[{i}]")


def build_product_line_summaries(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          l.side, l.line_kind, l.quantity, l.unit, l.currency, l.line_net_amount,
          p.name AS product_name, p.category
        FROM commercial_deal_line l
        LEFT JOIN commercial_product p ON p.id = l.product_id
        WHERE l.deal_id = ?
        ORDER BY l.side, l.line_number
        """,
        (deal_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = _row_dict(row)
        item: dict[str, Any] = {
            "side": d.get("side"),
            "line_kind": d.get("line_kind"),
            "product_name": d.get("product_name"),
            "category": d.get("category"),
            "quantity": d.get("quantity"),
            "unit": d.get("unit"),
            "currency": d.get("currency"),
        }
        if d.get("line_net_amount") is not None:
            item["line_net_amount"] = int(d["line_net_amount"])
        out.append(item)
    return out


def build_cost_summaries_by_type(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          cost_kind,
          currency,
          SUM(COALESCE(amount_integer, 0)) AS total_amount_integer,
          COUNT(*) AS row_count
        FROM commercial_deal_cost
        WHERE deal_id = ?
        GROUP BY cost_kind, currency
        ORDER BY cost_kind, currency
        """,
        (deal_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = _row_dict(row)
        out.append(
            {
                "cost_kind": d.get("cost_kind"),
                "currency": d.get("currency"),
                "total_amount_integer": int(d["total_amount_integer"] or 0),
                "row_count": int(d["row_count"] or 0),
            }
        )
    return out


def build_payment_summaries_masked(conn: sqlite3.Connection, deal_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          direction, payment_method, paid_at, currency,
          amount_gross_integer, amount_net_integer, iva_amount_integer,
          amount_decimal, amount_minor,
          secondary_currency, secondary_amount_decimal, secondary_amount_minor
        FROM commercial_deal_payment
        WHERE deal_id = ?
        ORDER BY paid_at, direction
        """,
        (deal_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = _row_dict(row)
        item: dict[str, Any] = {
            "direction": d.get("direction"),
            "payment_method": d.get("payment_method"),
            "paid_at": d.get("paid_at"),
            "currency": d.get("currency"),
        }
        for key in (
            "amount_gross_integer",
            "amount_net_integer",
            "iva_amount_integer",
            "amount_minor",
            "secondary_amount_minor",
        ):
            if d.get(key) is not None:
                item[key] = int(d[key])
        for key in ("amount_decimal", "secondary_currency", "secondary_amount_decimal"):
            if d.get(key) is not None:
                item[key] = d[key]
        out.append(item)
    return out


def build_margin_blockers_list(
    conn: sqlite3.Connection,
    deal_key: str,
    margin_status: str,
) -> list[str]:
    if margin_status == "computed":
        return []
    try:
        return list(margin_blockers_for_deal(conn, deal_key))
    except KeyError:
        return []


def build_safe_deal_mirror_row(conn: sqlite3.Connection, deal_key: str) -> dict[str, Any] | None:
    """Assemble one redacted row for commercial.deal from SQLite."""
    header = conn.execute(
        """
        SELECT
          id, deal_key, client_org_name, supplier_org_name,
          deal_status, margin_status, reconciliation_status, freight_status,
          client_sale_net_clp, client_iva_amount_clp, client_sale_gross_clp,
          client_payment_received_clp,
          supplier_invoice_total_decimal, supplier_invoice_total_minor,
          supplier_amount_paid_decimal, supplier_amount_paid_minor,
          margin_net_clp, margin_notes, updated_at
        FROM commercial_deal
        WHERE deal_key = ?
        LIMIT 1
        """,
        (deal_key,),
    ).fetchone()
    if header is None:
        return None
    h = _row_dict(header)
    deal_id = int(h["id"])
    margin_status = str(h.get("margin_status") or "")
    margin_pct = margin_pct_from_notes(h.get("margin_notes"))
    row: dict[str, Any] = {
        "deal_key": str(h["deal_key"]),
        "client_org_name": str(h.get("client_org_name") or ""),
        "supplier_org_name": str(h.get("supplier_org_name") or ""),
        "deal_status": str(h.get("deal_status") or ""),
        "margin_status": margin_status,
        "reconciliation_status": h.get("reconciliation_status"),
        "freight_status": h.get("freight_status"),
        "client_sale_net_clp": h.get("client_sale_net_clp"),
        "client_iva_amount_clp": h.get("client_iva_amount_clp"),
        "client_sale_gross_clp": h.get("client_sale_gross_clp"),
        "client_payment_received_clp": h.get("client_payment_received_clp"),
        "supplier_invoice_total_decimal": h.get("supplier_invoice_total_decimal"),
        "supplier_invoice_total_minor": h.get("supplier_invoice_total_minor"),
        "supplier_amount_paid_decimal": h.get("supplier_amount_paid_decimal"),
        "supplier_amount_paid_minor": h.get("supplier_amount_paid_minor"),
        "margin_net_clp": h.get("margin_net_clp") if margin_status == "computed" else None,
        "margin_pct": margin_pct if margin_status == "computed" else None,
        "updated_at": h.get("updated_at"),
        "product_line_summaries": build_product_line_summaries(conn, deal_id),
        "cost_summaries_by_type": build_cost_summaries_by_type(conn, deal_id),
        "payment_summaries_masked": build_payment_summaries_masked(conn, deal_id),
        "margin_blockers": build_margin_blockers_list(conn, deal_key, margin_status),
    }
    assert_mirror_payload_safe(row)
    return row


def load_all_safe_deal_mirror_rows(
    conn: sqlite3.Connection,
    *,
    deal_key_filter: str | None = None,
) -> list[dict[str, Any]]:
    if not commercial_deal_tables_exist(conn):
        return []
    if deal_key_filter:
        row = build_safe_deal_mirror_row(conn, deal_key_filter.strip())
        return [row] if row else []
    keys = conn.execute(
        "SELECT deal_key FROM commercial_deal ORDER BY updated_at DESC, deal_key"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for (deal_key,) in keys:
        built = build_safe_deal_mirror_row(conn, str(deal_key))
        if built:
            out.append(built)
    return out


def count_sqlite_deals(conn: sqlite3.Connection) -> int:
    if not commercial_deal_tables_exist(conn):
        return 0
    row = conn.execute("SELECT COUNT(*) FROM commercial_deal").fetchone()
    return int(row[0] if row else 0)
