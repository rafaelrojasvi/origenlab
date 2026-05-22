"""Dashboard summary counts over Postgres mart/outbound mirrors (read-only)."""

from __future__ import annotations

from psycopg import Connection

from origenlab_email_pipeline.operational_scope import (
    ARCHIVE_SCOPE_NOTE,
    CANONICAL_SCOPE_NOTE,
    normalize_data_scope,
    postgres_mart_relation,
)

from origenlab_email_pipeline.postgres_dashboard_api.db import (
    fetch_one,
    safe_count,
    table_exists,
)
from origenlab_email_pipeline.postgres_dashboard_api.mart_scope import (
    mart_base_table,
    resolve_mart_scope,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import DashboardSummaryResponse

COMMERCIAL_PURCHASE_EVENT_TABLE = ("commercial", "purchase_event")
COMMERCIAL_PURCHASE_ITEM_TABLE = ("commercial", "purchase_event_item")


def dashboard_summary(
    conn: Connection, *, scope: str | None = "canonical"
) -> DashboardSummaryResponse:
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
        rel, exists, note = resolve_mart_scope(conn, base=base, scope=sc)
        tables[rel] = exists
        if sc == "canonical" and not exists:
            scope_available = False
            scope_note = note
        elif exists:
            _, n = safe_count(conn, schema="mart", table=mart_base_table(rel))
            counts[key] = n
        if sc == "canonical":
            arch_rel = postgres_mart_relation(base, "archive")
            if table_exists(conn, schema="mart", table=mart_base_table(arch_rel)):
                _, arch_n = safe_count(conn, schema="mart", table=mart_base_table(arch_rel))
                archive_mirror[key] = arch_n

    for schema, table, key in outbound_specs:
        exists, n = safe_count(conn, schema=schema, table=table)
        tables[f"{schema}.{table}"] = exists
        counts[key] = n

    purchase_event_count = 0
    purchase_item_count = 0
    latest_gross: int | None = None
    pe_schema, pe_table = COMMERCIAL_PURCHASE_EVENT_TABLE
    pi_schema, pi_table = COMMERCIAL_PURCHASE_ITEM_TABLE
    pe_exists = table_exists(conn, schema=pe_schema, table=pe_table)
    tables[f"{pe_schema}.{pe_table}"] = pe_exists
    tables[f"{pi_schema}.{pi_table}"] = table_exists(conn, schema=pi_schema, table=pi_table)
    if pe_exists:
        _, purchase_event_count = safe_count(conn, schema=pe_schema, table=pe_table)
        if table_exists(conn, schema=pi_schema, table=pi_table):
            _, purchase_item_count = safe_count(conn, schema=pi_schema, table=pi_table)
        latest = fetch_one(
            conn,
            f"""
            SELECT gross_amount_clp
            FROM {pe_schema}.{pe_table}
            WHERE gross_amount_clp IS NOT NULL
            ORDER BY email_date_iso DESC NULLS LAST, id DESC
            LIMIT 1
            """,
        )
        if latest and latest.get("gross_amount_clp") is not None:
            latest_gross = int(latest["gross_amount_clp"])

    return DashboardSummaryResponse(
        tables=tables,
        scope=sc,
        scope_available=scope_available,
        scope_note=scope_note,
        archive_mirror_counts=archive_mirror,
        commercial_purchase_event_count=purchase_event_count,
        commercial_purchase_event_item_count=purchase_item_count,
        latest_confirmed_purchase_gross_clp=latest_gross,
        **counts,
    )
