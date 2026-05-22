"""Read-only canonical Gmail classification mirror queries (API-3 shared)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import DEFAULT_MAX_LIMIT
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    ClassificationActionGroup,
    ClassificationActionsResponse,
    ClassificationEmailRow,
    ClassificationRecentResponse,
    ClassificationSummaryResponse,
)

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


def _contact_from_addrs(
    from_addr: str | None, to_addrs: str | None
) -> tuple[str | None, str | None]:
    candidates = emails_in(from_addr or "") or emails_in(to_addrs or "")
    if not candidates:
        return None, None
    email = candidates[0].lower().strip()
    return email, domain_of(email)


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
    counts_by_label = {
        str(r["predicted_label"]): int(r["n"]) for r in rows if r.get("predicted_label")
    }
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
