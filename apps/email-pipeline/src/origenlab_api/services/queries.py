"""Postgres read queries for dashboard API (Slice 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.business_mart import domain_of, emails_in

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
    ClassificationActionGroup,
    ClassificationActionsResponse,
    ClassificationEmailRow,
    ClassificationRecentResponse,
    ClassificationSummaryResponse,
    ContactRow,
    DashboardSummaryResponse,
    DashboardSyncMetaResponse,
    EmailSuppressionRow,
    OrganizationRow,
    OutboundReadinessResponse,
    OutreachContactStateRow,
    PaginatedContactsResponse,
    PaginatedEmailSuppressionsResponse,
    PaginatedOrganizationsResponse,
    PaginatedOutreachStateResponse,
    POSTGRES_MIRROR_NOTE,
)

DEFAULT_MAX_LIMIT = 200
CLASSIFICATION_TABLE = ("reporting", "email_classification_canonical")

ACTION_LABELS_ES: dict[str, str] = {
    "responder_solicitud": "Responder posible solicitud",
    "revisar_cotizacion": "Revisar posible cotización",
    "revisar_seguimiento": "Revisar seguimiento",
    "marcar_rebote": "Marcar rebote probable",
    "revisar_proveedor": "Revisar proveedor",
    "revisar_manual": "Revisión manual",
    "revisar_cliente_activo": "Revisar cliente activo / compra",
    "revisar_historico": "Revisar histórico",
    "ignorar_notificacion": "Ignorar notificación",
}


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_seconds(
    started_at: datetime | str | None,
    finished_at: datetime | str | None,
) -> float | None:
    started = _parse_dt(started_at)
    finished = _parse_dt(finished_at)
    if started is None or finished is None:
        return None
    return round((finished - started).total_seconds(), 3)


def _classification_kpi(counts_by_label: dict[str, int]) -> dict[str, int]:
    return {
        "posibles_solicitudes": int(counts_by_label.get("quote_request_inbound", 0)),
        "cotizaciones_enviadas": int(counts_by_label.get("cotizacion_sent", 0)),
        "seguimientos": int(counts_by_label.get("needs_follow_up", 0))
        + int(counts_by_label.get("no_response_after_sent", 0)),
        "rebotes_malos_correos": int(counts_by_label.get("bad_email_or_bounce", 0)),
        "proveedores": int(counts_by_label.get("supplier_or_vendor", 0)),
        "sin_clasificar": int(counts_by_label.get("unclassified", 0)),
        "posibles_compras": int(counts_by_label.get("purchase_or_order_signal", 0)),
    }


def _contact_from_addrs(from_addr: str | None, to_addrs: str | None) -> tuple[str | None, str | None]:
    candidates = emails_in(from_addr or "") or emails_in(to_addrs or "")
    if not candidates:
        return None, None
    email = candidates[0].lower().strip()
    return email, domain_of(email)


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


def latest_dashboard_sync(conn: Connection) -> DashboardSyncMetaResponse:
    """Return the most recent reporting.dashboard_sync_run row, if any."""
    if not table_exists(conn, schema="reporting", table="dashboard_sync_run"):
        return DashboardSyncMetaResponse(table_available=False, status="missing_table")

    row = fetch_one(
        conn,
        """
        SELECT
          id,
          started_at,
          finished_at,
          status,
          canonical_contact_count,
          canonical_organization_count,
          canonical_opportunity_signal_count,
          archive_contact_count,
          archive_organization_count,
          archive_opportunity_signal_count,
          email_suppression_count,
          domain_suppression_count,
          outreach_state_count,
          error_message
        FROM reporting.dashboard_sync_run
        ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
        LIMIT 1
        """,
    )
    if not row:
        return DashboardSyncMetaResponse(table_available=True, status="no_rows")

    raw_status = str(row.get("status") or "unknown").strip().lower()
    if raw_status in ("success", "failed", "dry_run"):
        mapped_status = raw_status
    else:
        mapped_status = "unknown"

    started_at = row.get("started_at")
    finished_at = row.get("finished_at")
    return DashboardSyncMetaResponse(
        table_available=True,
        status=mapped_status,  # type: ignore[arg-type]
        latest_sync_id=int(row["id"]) if row.get("id") is not None else None,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=_elapsed_seconds(started_at, finished_at),
        postgres_mirror_note=POSTGRES_MIRROR_NOTE,
        canonical_contact_count=int(row.get("canonical_contact_count") or 0),
        canonical_organization_count=int(row.get("canonical_organization_count") or 0),
        canonical_opportunity_signal_count=int(row.get("canonical_opportunity_signal_count") or 0),
        archive_contact_count=int(row.get("archive_contact_count") or 0),
        archive_organization_count=int(row.get("archive_organization_count") or 0),
        archive_opportunity_signal_count=int(row.get("archive_opportunity_signal_count") or 0),
        email_suppression_count=int(row.get("email_suppression_count") or 0),
        domain_suppression_count=int(row.get("domain_suppression_count") or 0),
        outreach_state_count=int(row.get("outreach_state_count") or 0),
        error_message=row.get("error_message"),
    )


def classification_summary(conn: Connection) -> ClassificationSummaryResponse:
    schema, table = CLASSIFICATION_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return ClassificationSummaryResponse(table_available=False, status="missing_table")

    total_row = fetch_one(conn, f"SELECT COUNT(*)::bigint AS n FROM {schema}.{table}")
    total = int((total_row or {}).get("n") or 0)
    if total == 0:
        return ClassificationSummaryResponse(
            table_available=True, status="no_rows", total_rows=0
        )

    rows = fetch_all(
        conn,
        f"""
        SELECT predicted_label, COUNT(*)::bigint AS n
        FROM {schema}.{table}
        WHERE source_scope = 'canonical'
        GROUP BY predicted_label
        """,
    )
    counts_by_label = {str(r["predicted_label"]): int(r["n"]) for r in rows if r.get("predicted_label")}
    return ClassificationSummaryResponse(
        table_available=True,
        status="ok",
        total_rows=total,
        counts_by_label=counts_by_label,
        kpi=_classification_kpi(counts_by_label),
    )


def classification_recent(
    conn: Connection,
    *,
    label: str | None = None,
    limit: int = 20,
) -> ClassificationRecentResponse:
    schema, table = CLASSIFICATION_TABLE
    lim = max(1, min(int(limit), DEFAULT_MAX_LIMIT))
    if not table_exists(conn, schema=schema, table=table):
        return ClassificationRecentResponse(table_available=False, limit=lim, label_filter=label)

    where = ["source_scope = 'canonical'"]
    params: list[Any] = []
    if label and label.strip():
        where.append("predicted_label = %s")
        params.append(label.strip())
    where_sql = " AND ".join(where)

    total_row = fetch_one(
        conn,
        f"SELECT COUNT(*)::bigint AS n FROM {schema}.{table} WHERE {where_sql}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    rows = fetch_all(
        conn,
        f"""
        SELECT email_id, date_iso, folder, from_addr, to_addrs, subject,
               predicted_label, confidence, ambiguous, recommended_action,
               etiqueta_ui, evidence
        FROM {schema}.{table}
        WHERE {where_sql}
        ORDER BY date_iso DESC NULLS LAST, email_id DESC
        LIMIT %s
        """,
        tuple(params) + (lim,),
    )
    items: list[ClassificationEmailRow] = []
    for r in rows:
        contact_email, contact_domain = _contact_from_addrs(r.get("from_addr"), r.get("to_addrs"))
        items.append(
            ClassificationEmailRow(
                email_id=int(r["email_id"]),
                date_iso=r.get("date_iso"),
                folder=r.get("folder"),
                from_addr=r.get("from_addr"),
                to_addrs=r.get("to_addrs"),
                subject=r.get("subject"),
                predicted_label=str(r.get("predicted_label") or "unclassified"),
                confidence=str(r.get("confidence") or ""),
                ambiguous=bool(r.get("ambiguous")),
                recommended_action=str(r.get("recommended_action") or "revisar_manual"),
                etiqueta_ui=str(r.get("etiqueta_ui") or ""),
                evidence=r.get("evidence"),
                contact_email=contact_email,
                contact_domain=contact_domain,
            )
        )
    return ClassificationRecentResponse(
        table_available=True,
        items=items,
        total=total,
        limit=lim,
        label_filter=label.strip() if label and label.strip() else None,
    )


def classification_actions(conn: Connection) -> ClassificationActionsResponse:
    schema, table = CLASSIFICATION_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return ClassificationActionsResponse(table_available=False)

    rows = fetch_all(
        conn,
        f"""
        SELECT recommended_action, COUNT(*)::bigint AS n
        FROM {schema}.{table}
        WHERE source_scope = 'canonical'
        GROUP BY recommended_action
        ORDER BY n DESC, recommended_action ASC
        """,
    )
    groups: list[ClassificationActionGroup] = []
    for r in rows:
        action = str(r.get("recommended_action") or "revisar_manual")
        sample_rows = fetch_all(
            conn,
            f"""
            SELECT subject
            FROM {schema}.{table}
            WHERE source_scope = 'canonical' AND recommended_action = %s
            ORDER BY date_iso DESC NULLS LAST
            LIMIT 3
            """,
            (action,),
        )
        samples = [str(s.get("subject") or "").strip() for s in sample_rows if s.get("subject")]
        groups.append(
            ClassificationActionGroup(
                recommended_action=action,
                action_label_es=ACTION_LABELS_ES.get(action, action.replace("_", " ")),
                count=int(r.get("n") or 0),
                sample_subjects=samples,
            )
        )
    return ClassificationActionsResponse(table_available=True, groups=groups)


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
