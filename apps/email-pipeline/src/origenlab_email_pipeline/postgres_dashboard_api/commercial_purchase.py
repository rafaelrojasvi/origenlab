"""Read-only confirmed purchase order events (Postgres commercial mirror)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, safe_count, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import DEFAULT_MAX_LIMIT
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    COMMERCIAL_PURCHASE_DISCLAIMER,
    CommercialPurchaseEventDetailResponse,
    CommercialPurchaseEventItemRow,
    CommercialPurchaseEventRow,
    CommercialPurchaseEventsListResponse,
)

COMMERCIAL_PURCHASE_EVENT_TABLE = ("commercial", "purchase_event")
COMMERCIAL_PURCHASE_ITEM_TABLE = ("commercial", "purchase_event_item")

PURCHASE_STATUS_LABELS_ES: dict[str, str] = {
    "purchase_order_received": "OC recibida",
    "buyer_confirmed_oc_received": "OC confirmada",
}

DEFAULT_PURCHASE_SUGGESTED_ACTION_ES = (
    "Confirmar despacho, enviar factura y datos bancarios"
)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _purchase_status_label_es(status: str) -> str:
    return PURCHASE_STATUS_LABELS_ES.get(status, status.replace("_", " "))


def _product_summary_from_items(items: list[CommercialPurchaseEventItemRow]) -> str:
    names = [i.product_name for i in items if i.product_name]
    if not names:
        return ""
    return "; ".join(names[:5])


def _row_to_purchase_event(
    row: dict[str, Any],
    items: list[CommercialPurchaseEventItemRow],
) -> CommercialPurchaseEventRow:
    status = str(row.get("purchase_status") or "")
    dispatch = bool(row.get("dispatch_requested"))
    invoice = bool(row.get("invoice_requested"))
    bank = bool(row.get("bank_details_requested"))
    suggested = None
    if dispatch or invoice or bank:
        suggested = DEFAULT_PURCHASE_SUGGESTED_ACTION_ES
    return CommercialPurchaseEventRow(
        id=int(row["id"]),
        source_email_id=int(row["source_email_id"]) if row.get("source_email_id") else None,
        buyer_org_name=str(row.get("buyer_org_name") or ""),
        buyer_contact_name=row.get("buyer_contact_name"),
        buyer_contact_email=row.get("buyer_contact_email"),
        buyer_domain=row.get("buyer_domain"),
        purchase_status=status,
        purchase_status_label_es=_purchase_status_label_es(status),
        oc_number=str(row.get("oc_number") or ""),
        quote_number=row.get("quote_number"),
        project_name=row.get("project_name"),
        project_code=row.get("project_code"),
        net_amount_clp=int(row["net_amount_clp"]) if row.get("net_amount_clp") is not None else None,
        iva_amount_clp=int(row["iva_amount_clp"]) if row.get("iva_amount_clp") is not None else None,
        gross_amount_clp=int(row["gross_amount_clp"])
        if row.get("gross_amount_clp") is not None
        else None,
        currency=str(row.get("currency") or "CLP"),
        email_date_iso=row.get("email_date_iso"),
        email_subject=row.get("email_subject"),
        commercial_summary=row.get("commercial_summary"),
        suggested_action_es=suggested,
        line_items=items,
        product_summary=_product_summary_from_items(items),
    )


def _fetch_purchase_event_items(
    conn: Connection,
    event_ids: list[int],
) -> dict[int, list[CommercialPurchaseEventItemRow]]:
    if not event_ids:
        return {}
    schema, table = COMMERCIAL_PURCHASE_ITEM_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return {}
    ph = ",".join("%s" for _ in event_ids)
    rows = fetch_all(
        conn,
        f"""
        SELECT purchase_event_id, line_number, ref_code, product_name, brand,
               quantity, net_amount_clp, evidence_source
        FROM {schema}.{table}
        WHERE purchase_event_id IN ({ph})
        ORDER BY purchase_event_id, line_number
        """,
        tuple(event_ids),
    )
    out: dict[int, list[CommercialPurchaseEventItemRow]] = {}
    for r in rows:
        eid = int(r["purchase_event_id"])
        out.setdefault(eid, []).append(
            CommercialPurchaseEventItemRow(
                line_number=int(r["line_number"]),
                ref_code=r.get("ref_code"),
                product_name=str(r.get("product_name") or ""),
                brand=r.get("brand"),
                quantity=r.get("quantity"),
                net_amount_clp=int(r["net_amount_clp"])
                if r.get("net_amount_clp") is not None
                else None,
                evidence_source=r.get("evidence_source"),
            )
        )
    return out


def list_commercial_purchase_events(
    conn: Connection,
    *,
    limit: int = 20,
) -> CommercialPurchaseEventsListResponse:
    limit = _clamp_limit(limit)
    schema, table = COMMERCIAL_PURCHASE_EVENT_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return CommercialPurchaseEventsListResponse(
            table_available=False,
            items=[],
            total=0,
            limit=limit,
        )
    _, total = safe_count(conn, schema=schema, table=table)
    rows = fetch_all(
        conn,
        f"""
        SELECT id, source_email_id, buyer_org_name, buyer_contact_name, buyer_contact_email,
               buyer_domain, purchase_status, oc_number, quote_number, project_name, project_code,
               net_amount_clp, iva_amount_clp, gross_amount_clp, currency, email_date_iso,
               email_subject, commercial_summary,
               dispatch_requested, invoice_requested, bank_details_requested
        FROM {schema}.{table}
        ORDER BY email_date_iso DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    event_ids = [int(r["id"]) for r in rows]
    items_by_event = _fetch_purchase_event_items(conn, event_ids)
    items_out = [
        _row_to_purchase_event(r, items_by_event.get(int(r["id"]), [])) for r in rows
    ]
    return CommercialPurchaseEventsListResponse(
        table_available=True,
        items=items_out,
        total=total,
        limit=limit,
        disclaimer=COMMERCIAL_PURCHASE_DISCLAIMER,
    )


def get_commercial_purchase_event(
    conn: Connection,
    *,
    event_id: int,
) -> CommercialPurchaseEventDetailResponse:
    schema, table = COMMERCIAL_PURCHASE_EVENT_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return CommercialPurchaseEventDetailResponse(table_available=False, event=None)
    row = fetch_one(
        conn,
        f"""
        SELECT id, source_email_id, buyer_org_name, buyer_contact_name, buyer_contact_email,
               buyer_domain, purchase_status, oc_number, quote_number, project_name, project_code,
               net_amount_clp, iva_amount_clp, gross_amount_clp, currency, email_date_iso,
               email_subject, commercial_summary,
               dispatch_requested, invoice_requested, bank_details_requested
        FROM {schema}.{table}
        WHERE id = %s
        LIMIT 1
        """,
        (event_id,),
    )
    if not row:
        return CommercialPurchaseEventDetailResponse(table_available=True, event=None)
    items = _fetch_purchase_event_items(conn, [event_id]).get(event_id, [])
    return CommercialPurchaseEventDetailResponse(
        table_available=True,
        event=_row_to_purchase_event(row, items),
        disclaimer=COMMERCIAL_PURCHASE_DISCLAIMER,
    )
