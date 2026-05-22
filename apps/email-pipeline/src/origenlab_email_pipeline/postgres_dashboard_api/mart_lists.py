"""Paginated read-only mart contact and organization lists (Postgres mirror)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.operational_scope import normalize_data_scope
from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one
from origenlab_email_pipeline.postgres_dashboard_api.mart_scope import resolve_mart_scope
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import DEFAULT_MAX_LIMIT
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    ContactRow,
    OrganizationRow,
    PaginatedContactsResponse,
    PaginatedOrganizationsResponse,
)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _clamp_offset(offset: int) -> int:
    return max(0, int(offset))


def list_contacts(
    conn: Connection,
    *,
    limit: int,
    offset: int,
    domain: str | None,
    q: str | None,
    scope: str | None = "canonical",
) -> PaginatedContactsResponse:
    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)
    sc = normalize_data_scope(scope)
    rel, available, note = resolve_mart_scope(conn, base="contact_master", scope=sc)
    if not available:
        return PaginatedContactsResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
            table_available=False,
            scope=sc,
            scope_available=False,
            scope_note=note,
        )

    where: list[str] = []
    params: list[Any] = []
    if domain and domain.strip():
        where.append("domain = %s")
        params.append(domain.strip().lower())
    if q and q.strip():
        where.append(
            "(email ILIKE %s OR COALESCE(contact_name_best, '') ILIKE %s "
            "OR COALESCE(organization_name_guess, '') ILIKE %s)"
        )
        pat = f"%{q.strip()}%"
        params.extend([pat, pat, pat])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total_row = fetch_one(
        conn,
        f"SELECT COUNT(*)::bigint AS n FROM {rel}{where_sql}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    rows = fetch_all(
        conn,
        f"""
        SELECT email, contact_name_best, domain, organization_name_guess,
               organization_type_guess, first_seen_at, last_seen_at,
               total_emails, confidence_score, top_equipment_tags
        FROM {rel}
        {where_sql}
        ORDER BY last_seen_at DESC NULLS LAST, email ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params) + (limit, offset),
    )
    items = [ContactRow.model_validate(r) for r in rows]
    return PaginatedContactsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        table_available=True,
        scope=sc,
        scope_available=True,
        scope_note=note,
    )


def list_organizations(
    conn: Connection,
    *,
    limit: int,
    offset: int,
    domain: str | None,
    q: str | None,
    scope: str | None = "canonical",
) -> PaginatedOrganizationsResponse:
    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)
    sc = normalize_data_scope(scope)
    rel, available, note = resolve_mart_scope(
        conn, base="organization_master", scope=sc
    )
    if not available:
        return PaginatedOrganizationsResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
            table_available=False,
            scope=sc,
            scope_available=False,
            scope_note=note,
        )

    where: list[str] = []
    params: list[Any] = []
    if domain and domain.strip():
        where.append("domain = %s")
        params.append(domain.strip().lower())
    if q and q.strip():
        where.append(
            "(domain ILIKE %s OR COALESCE(organization_name_guess, '') ILIKE %s)"
        )
        pat = f"%{q.strip()}%"
        params.extend([pat, pat])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total_row = fetch_one(
        conn,
        f"SELECT COUNT(*)::bigint AS n FROM {rel}{where_sql}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    rows = fetch_all(
        conn,
        f"""
        SELECT domain, organization_name_guess, organization_type_guess,
               first_seen_at, last_seen_at, total_emails, total_contacts,
               top_equipment_tags, key_contacts
        FROM {rel}
        {where_sql}
        ORDER BY last_seen_at DESC NULLS LAST, domain ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params) + (limit, offset),
    )
    items = [OrganizationRow.model_validate(r) for r in rows]
    return PaginatedOrganizationsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        table_available=True,
        scope=sc,
        scope_available=True,
        scope_note=note,
    )
