"""Read-only redacted commercial deal ledger (Postgres commercial.deal mirror)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, safe_count, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import DEFAULT_MAX_LIMIT
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    COMMERCIAL_DEAL_DISCLAIMER,
    CommercialDealDetailResponse,
    CommercialDealRow,
    CommercialDealsListResponse,
)

COMMERCIAL_DEAL_TABLE = ("commercial", "deal")

_DEAL_SELECT = """
SELECT
  deal_key, client_org_name, supplier_org_name,
  deal_status, margin_status, reconciliation_status, freight_status,
  client_sale_net_clp, client_iva_amount_clp, client_sale_gross_clp,
  client_payment_received_clp,
  supplier_invoice_total_decimal, supplier_invoice_total_minor,
  supplier_amount_paid_decimal, supplier_amount_paid_minor,
  margin_net_clp, margin_pct, updated_at,
  product_line_summaries, cost_summaries_by_type,
  payment_summaries_masked, margin_blockers
FROM {schema}.{table}
"""


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _row_to_deal(row: dict[str, Any]) -> CommercialDealRow:
    payload = dict(row)
    for key in (
        "product_line_summaries",
        "cost_summaries_by_type",
        "payment_summaries_masked",
        "margin_blockers",
    ):
        if payload.get(key) is None:
            payload[key] = []
    return CommercialDealRow.model_validate(payload)


def list_commercial_deals(
    conn: Connection,
    *,
    limit: int = 20,
) -> CommercialDealsListResponse:
    limit = _clamp_limit(limit)
    schema, table = COMMERCIAL_DEAL_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return CommercialDealsListResponse(
            table_available=False,
            items=[],
            total=0,
            limit=limit,
        )
    _, total = safe_count(conn, schema=schema, table=table)
    rows = fetch_all(
        conn,
        _DEAL_SELECT.format(schema=schema, table=table)
        + " ORDER BY updated_at DESC NULLS LAST, deal_key LIMIT %s",
        (limit,),
    )
    items = [_row_to_deal(r) for r in rows]
    return CommercialDealsListResponse(
        table_available=True,
        items=items,
        total=total,
        limit=limit,
        disclaimer=COMMERCIAL_DEAL_DISCLAIMER,
    )


def get_commercial_deal(
    conn: Connection,
    *,
    deal_key: str,
) -> CommercialDealDetailResponse:
    schema, table = COMMERCIAL_DEAL_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return CommercialDealDetailResponse(table_available=False, deal=None)
    row = fetch_one(
        conn,
        _DEAL_SELECT.format(schema=schema, table=table) + " WHERE deal_key = %s LIMIT 1",
        (deal_key.strip(),),
    )
    if not row:
        return CommercialDealDetailResponse(table_available=True, deal=None)
    return CommercialDealDetailResponse(
        table_available=True,
        deal=_row_to_deal(row),
        disclaimer=COMMERCIAL_DEAL_DISCLAIMER,
    )
