"""Paginated read-only outbound mirror lists (suppressions, contact state)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    EmailSuppressionRow,
    OutreachContactStateRow,
    PaginatedEmailSuppressionsResponse,
    PaginatedOutreachStateResponse,
)

DEFAULT_MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _clamp_offset(offset: int) -> int:
    return max(0, int(offset))


def list_email_suppressions(
    conn: Connection,
    *,
    limit: int,
    offset: int,
    q: str | None,
) -> PaginatedEmailSuppressionsResponse:
    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)
    if not table_exists(conn, schema="outbound", table="contact_email_suppression"):
        return PaginatedEmailSuppressionsResponse(
            items=[], total=0, limit=limit, offset=offset, table_available=False
        )

    where_sql = ""
    params: list[Any] = []
    if q and q.strip():
        where_sql = " WHERE email ILIKE %s"
        params.append(f"%{q.strip()}%")

    total_row = fetch_one(
        conn,
        f"SELECT COUNT(*)::bigint AS n FROM outbound.contact_email_suppression{where_sql}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    rows = fetch_all(
        conn,
        f"""
        SELECT email, suppression_reason_code, suppression_reason_text,
               suppression_source, last_bounced_at, updated_at, updated_by
        FROM outbound.contact_email_suppression
        {where_sql}
        ORDER BY updated_at DESC NULLS LAST, email ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params) + (limit, offset),
    )
    items = [EmailSuppressionRow.model_validate(r) for r in rows]
    return PaginatedEmailSuppressionsResponse(
        items=items, total=total, limit=limit, offset=offset, table_available=True
    )


def list_outreach_contact_state(
    conn: Connection,
    *,
    limit: int,
    offset: int,
    state: str | None,
    q: str | None,
) -> PaginatedOutreachStateResponse:
    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)
    if not table_exists(conn, schema="outbound", table="outreach_contact_state"):
        return PaginatedOutreachStateResponse(
            items=[], total=0, limit=limit, offset=offset, table_available=False
        )

    where: list[str] = []
    params: list[Any] = []
    if state and state.strip():
        where.append("lower(trim(state)) = %s")
        params.append(state.strip().lower())
    if q and q.strip():
        where.append("contact_email_norm ILIKE %s")
        params.append(f"%{q.strip().lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total_row = fetch_one(
        conn,
        f"SELECT COUNT(*)::bigint AS n FROM outbound.outreach_contact_state{where_sql}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    rows = fetch_all(
        conn,
        f"""
        SELECT contact_email_norm, state, first_contacted_at, last_contacted_at,
               source, notes, updated_at, updated_by, lead_id
        FROM outbound.outreach_contact_state
        {where_sql}
        ORDER BY updated_at DESC NULLS LAST, contact_email_norm ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params) + (limit, offset),
    )
    items = [OutreachContactStateRow.model_validate(r) for r in rows]
    return PaginatedOutreachStateResponse(
        items=items, total=total, limit=limit, offset=offset, table_available=True
    )
