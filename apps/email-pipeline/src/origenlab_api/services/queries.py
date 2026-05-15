"""Postgres read queries for dashboard API (Slice 1)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.operational_scope import (
    ARCHIVE_SCOPE_NOTE,
    CANONICAL_POSTGRES_UNAVAILABLE_NOTE,
    CANONICAL_SCOPE_NOTE,
    DataScope,
    normalize_data_scope,
    postgres_mart_relation,
)

from origenlab_api.db import fetch_all, fetch_one, safe_count, table_exists
from origenlab_api.schemas import (
    ContactRow,
    DashboardSummaryResponse,
    EmailSuppressionRow,
    OrganizationRow,
    OutboundReadinessResponse,
    OutreachContactStateRow,
    PaginatedContactsResponse,
    PaginatedEmailSuppressionsResponse,
    PaginatedOrganizationsResponse,
    PaginatedOutreachStateResponse,
)

DEFAULT_MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _clamp_offset(offset: int) -> int:
    return max(0, int(offset))


def _mart_base_table(relation: str) -> str:
    return relation.split(".", 1)[1]


def _resolve_mart_scope(
    conn: Connection,
    *,
    base: str,
    scope: DataScope,
) -> tuple[str, bool, str]:
    """Return (fully-qualified relation, scope_available, scope_note)."""
    if scope == "archive":
        rel = postgres_mart_relation(base, "archive")
        exists = table_exists(conn, schema="mart", table=_mart_base_table(rel))
        return rel, exists, ARCHIVE_SCOPE_NOTE
    rel = postgres_mart_relation(base, "canonical")
    exists = table_exists(conn, schema="mart", table=_mart_base_table(rel))
    if exists:
        return rel, True, CANONICAL_SCOPE_NOTE
    return rel, False, CANONICAL_POSTGRES_UNAVAILABLE_NOTE


def dashboard_summary(conn: Connection, *, scope: str | None = "canonical") -> DashboardSummaryResponse:
    sc = normalize_data_scope(scope)
    mart_specs = (
        ("contact_master", "contact_count"),
        ("organization_master", "organization_count"),
        ("opportunity_signals", "opportunity_signal_count"),
    )
    outbound_specs = (
        ("outbound", "contact_email_suppression", "email_suppression_count"),
        ("outbound", "contact_domain_suppression", "domain_suppression_count"),
        ("outbound", "outreach_contact_state", "outreach_state_count"),
    )
    tables: dict[str, bool] = {}
    counts: dict[str, int] = {
        "contact_count": 0,
        "organization_count": 0,
        "opportunity_signal_count": 0,
        "email_suppression_count": 0,
        "domain_suppression_count": 0,
        "outreach_state_count": 0,
    }
    scope_note = CANONICAL_SCOPE_NOTE if sc == "canonical" else ARCHIVE_SCOPE_NOTE
    scope_available = True
    archive_mirror: dict[str, int] = {}

    for base, key in mart_specs:
        rel, exists, note = _resolve_mart_scope(conn, base=base, scope=sc)
        tables[rel] = exists
        if sc == "canonical" and not exists:
            scope_available = False
            scope_note = note
        elif exists:
            _, n = safe_count(conn, schema="mart", table=_mart_base_table(rel))
            counts[key] = n
        if sc == "canonical":
            arch_rel = postgres_mart_relation(base, "archive")
            if table_exists(conn, schema="mart", table=_mart_base_table(arch_rel)):
                _, arch_n = safe_count(conn, schema="mart", table=_mart_base_table(arch_rel))
                archive_mirror[key] = arch_n

    for schema, table, key in outbound_specs:
        exists, n = safe_count(conn, schema=schema, table=table)
        tables[f"{schema}.{table}"] = exists
        counts[key] = n

    return DashboardSummaryResponse(
        tables=tables,
        scope=sc,
        scope_available=scope_available,
        scope_note=scope_note,
        archive_mirror_counts=archive_mirror,
        **counts,
    )


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
    rel, available, note = _resolve_mart_scope(conn, base="contact_master", scope=sc)
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
    rel, available, note = _resolve_mart_scope(conn, base="organization_master", scope=sc)
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


def assess_postgres_outbound_readiness(
    conn: Connection,
    *,
    postgres_url_redacted: str,
    gmail_user: str,
    max_staleness_days: float = 30.0,
) -> OutboundReadinessResponse:
    """Read-only readiness from Postgres mirrors (not full SQLite preflight)."""
    warnings: list[str] = []
    errors: list[str] = []

    tier_tables = {
        "mart.contact_master": ("mart", "contact_master"),
        "mart.organization_master": ("mart", "organization_master"),
        "mart.opportunity_signals": ("mart", "opportunity_signals"),
        "outbound.contact_email_suppression": ("outbound", "contact_email_suppression"),
        "outbound.contact_domain_suppression": ("outbound", "contact_domain_suppression"),
        "outbound.outreach_contact_state": ("outbound", "outreach_contact_state"),
    }
    tables: dict[str, bool] = {}
    counts: dict[str, int] = {}
    for label, (schema, table) in tier_tables.items():
        exists, n = safe_count(conn, schema=schema, table=table)
        tables[label] = exists
        counts[label.replace(".", "_") + "_rows"] = n
        if not exists:
            warnings.append(f"Postgres table missing: {label} (run Alembic / Tier A sync).")

    mart: dict[str, Any] = {}
    if tables.get("mart.contact_master"):
        r = fetch_one(conn, "SELECT MAX(last_seen_at) AS m FROM mart.contact_master")
        mart["contact_master_max_last_seen"] = r.get("m") if r else None
    if tables.get("mart.organization_master"):
        r = fetch_one(conn, "SELECT MAX(last_seen_at) AS m FROM mart.organization_master")
        mart["organization_master_max_last_seen"] = r.get("m") if r else None
    if tables.get("mart.opportunity_signals"):
        r = fetch_one(conn, "SELECT MAX(created_at) AS m FROM mart.opportunity_signals")
        mart["opportunity_signals_max_created_at"] = r.get("m") if r else None

    sidecars: dict[str, Any] = {}
    if tables.get("outbound.contact_email_suppression"):
        sidecars["suppression_rows"] = counts.get("outbound_contact_email_suppression_rows", 0)
    if tables.get("outbound.outreach_contact_state"):
        row = fetch_one(
            conn,
            """
            SELECT COUNT(*)::bigint AS n
            FROM outbound.outreach_contact_state
            WHERE state IN ('contacted', 'replied', 'snoozed')
              AND length(trim(contact_email_norm)) > 0
            """,
        )
        sidecars["outreach_blocking_rows"] = int((row or {}).get("n") or 0)
        states = fetch_all(
            conn,
            """
            SELECT lower(trim(state)) AS st, COUNT(*)::bigint AS n
            FROM outbound.outreach_contact_state
            WHERE state IN ('contacted', 'replied', 'snoozed')
              AND length(trim(contact_email_norm)) > 0
            GROUP BY 1
            """,
        )
        sidecars["outreach_by_state"] = {str(r["st"]): int(r["n"]) for r in states if r.get("st")}

    required_outbound = (
        "outbound.contact_email_suppression",
        "outbound.outreach_contact_state",
    )
    for label in required_outbound:
        if not tables.get(label):
            errors.append(f"Required mirror table missing: {label}")

    if tables.get("mart.contact_master") and counts.get("mart_contact_master_rows", 0) == 0:
        warnings.append("mart.contact_master is empty — run mart rebuild + sync to Postgres.")
    if tables.get("outbound.contact_email_suppression") and sidecars.get("suppression_rows", 0) == 0:
        warnings.append(
            "outbound.contact_email_suppression is empty — sync from SQLite or confirm suppression data."
        )

    warnings.append(
        "Sent-folder history is not evaluated here (requires SQLite `emails` ingest). "
        "Use CLI/Streamlit preflight for full gate readiness."
    )

    verdict: str = "ready"
    if errors:
        verdict = "not_ready"
    elif warnings:
        verdict = "ready_with_warnings"

    return OutboundReadinessResponse(
        verdict=verdict,  # type: ignore[arg-type]
        postgres_url_redacted=postgres_url_redacted,
        gmail_user=gmail_user,
        tables=tables,
        counts=counts,
        mart=mart,
        sidecars=sidecars,
        warnings=warnings,
        errors=errors,
    )
