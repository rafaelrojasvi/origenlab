"""Postgres mirror outbound readiness assessment (read-only report, not send permission)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, safe_count
from origenlab_email_pipeline.postgres_dashboard_api.schemas import OutboundReadinessResponse


def assess_postgres_outbound_readiness(
    conn: Connection,
    *,
    postgres_url_redacted: str,
    gmail_user: str,
    max_staleness_days: float = 30.0,
) -> OutboundReadinessResponse:
    """Read-only readiness from Postgres mirrors (not full SQLite preflight)."""
    _ = max_staleness_days  # reserved for future staleness checks; legacy API accepts the param
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
