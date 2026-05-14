from __future__ import annotations

import io
import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.marketing_contact_noise import (
    marketing_outreach_noise_email,
    marketing_outreach_noise_organization_guess,
)
from origenlab_email_pipeline.marketing_supplier_domains import (
    is_supplier_email_domain,
    supplier_email_domains,
)
from origenlab_email_pipeline.freshness_dates import MART_DATE_SLACK_DAYS_DEFAULT
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.contact_email_suppression import (
    SUPPRESSION_REASON_CODES,
    contact_email_suppression_table_exists,
    delete_contact_email_suppression,
    ensure_contact_email_suppression_table,
    fetch_contact_email_suppression_map,
    fetch_contact_email_suppression_row,
    streamlit_contact_suppression_rw_enabled,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)
from origenlab_email_pipeline.lead_contact_research import (
    CONTACT_RESEARCH_STATUSES,
    archive_org_hint_for_domain,
    delete_contact_research,
    fetch_contact_research_row,
    streamlit_leads_review_rw_enabled,
    upsert_contact_research,
    validate_contact_research_payload,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base
from origenlab_email_pipeline.streamlit_leads_browse import (
    LeadBrowseFilters,
    fetch_lead_account_rollups_df,
    fetch_leads_browse_df,
    lead_browse_filter_options,
    lead_browse_ready,
)
from origenlab_email_pipeline.streamlit_suppliers_browse import (
    SupplierBrowseFilters,
    fetch_suppliers_browse_df,
    supplier_browse_filter_options,
    supplier_browse_ready,
)
from origenlab_email_pipeline.streamlit_borrador_support import contact_suppression_reason_label
from origenlab_email_pipeline.streamlit_page_status import render_kpi_metric, render_page_status
from origenlab_email_pipeline.streamlit_prioridad_copy import (
    PRIORIDAD_DEL_DIA_GROUP_TITLE,
    PRIORIDAD_GROUP_NAV_CAPTION_ES,
)
from origenlab_email_pipeline.streamlit_prioridad_handoffs import (
    SESSION_CI_TODAY_HINT,
    SESSION_LEADS_TODAY_BANNER,
    SESSION_OPP_SIGNAL_FILTER,
    SESSION_START_PAGE,
    navigate_to_page,
)
from origenlab_email_pipeline.streamlit_prioridad_pages import (
    render_cases_to_review_page,
    render_commercial_draft_review_page,
    render_next_marketing_queue_page,
    render_que_hacer_hoy_page,
)
# Áreas de navegación: mismas vistas que antes, agrupadas para reducir ruido visual.
_NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("Resumen y sistema", ["Resumen", "Salud de datos", "Actividad contacto Gmail"]),
    (
        "Prioridad del día",
        ["Qué hacer hoy", "Casos para revisar", "Cola outreach marketing", "Borrador comercial"],
    ),
    (
        "Clientes e historial (archivo)",
        ["Candidatos comerciales", "Oportunidades", "Organizaciones", "Contactos", "Documentos", "Equipos"],
    ),
    ("Licitaciones / leads externos", ["Leads y cuentas", "Proveedores"]),
]


def _all_nav_pages() -> list[str]:
    return [p for _, lst in _NAV_GROUPS for p in lst]


def _nav_group_index_for_page(page: str) -> int:
    for i, (_, lst) in enumerate(_NAV_GROUPS):
        if page in lst:
            return i
    return 0


def _fmt_ci_entity_kind(v: str) -> str:
    return {
        "(todas)": "Todas las entidades",
        "organization": "Organización",
        "contact": "Contacto",
        "opportunity": "Oportunidad",
    }.get(v, v)


def _fmt_ci_status(v: str) -> str:
    return {
        "(todos)": "Todos los estados",
        "new": "Nuevo",
        "needs_review": "Pendiente de revisión",
        "approved": "Aprobado",
        "rejected": "Rechazado",
        "snoozed": "Pospuesto",
        "suppressed": "Suprimido",
    }.get(v, v)


def _fmt_ci_action(v: str) -> str:
    return {"approve": "Aprobar", "reject": "Rechazar", "snooze": "Posponer"}.get(v, v)


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    # Use immutable=1 so SQLite won't try to create -wal/-shm files.
    # This is important when the DB is volume-mounted read-only in Docker.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    """True if a table or view with this name exists (SQLite lists views separately)."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _ensure_lead_contact_research_ddl(db_path: Path) -> bool:
    """Apply leads DDL (including ``lead_contact_research``) via a writable handle.

    The Streamlit app uses a read-only immutable connection; existing DBs may lack newer
    tables until this runs once on a writable SQLite file.
    """
    try:
        w = sqlite3.connect(str(db_path.resolve()), timeout=60.0)
        try:
            if _has_table(w, "lead_contact_research"):
                return True
            ensure_leads_tables_ddl_base(w)
            w.commit()
            return _has_table(w, "lead_contact_research")
        finally:
            w.close()
    except sqlite3.Error:
        return False


def _load_df(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def _safe_count(conn: sqlite3.Connection, table: str) -> int | None:
    if not _has_table(conn, table):
        return None
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def _safe_scalar_sql(conn: sqlite3.Connection, sql: str) -> str | None:
    try:
        row = conn.execute(sql).fetchone()
        if not row or row[0] is None:
            return None
        s = str(row[0]).strip()
        return s if s else None
    except sqlite3.Error:
        return None


def _safe_scalar_sql_params(conn: sqlite3.Connection, sql: str, params: tuple) -> str | None:
    try:
        row = conn.execute(sql, params).fetchone()
        if not row or row[0] is None:
            return None
        s = str(row[0]).strip()
        return s if s else None
    except sqlite3.Error:
        return None


def _mart_plausible_max_ts(
    conn: sqlite3.Connection, table: str, column: str, slack_days: int
) -> str | None:
    """MAX(timestamp) excluding calendar dates beyond today+slack (matches mart rebuild + Salud de datos)."""
    allowed = frozenset(
        {
            ("contact_master", "last_seen_at"),
            ("organization_master", "last_seen_at"),
            ("document_master", "sent_at"),
        }
    )
    if (table, column) not in allowed:
        return None
    n = slack_days
    if n < 0 or n > 3660:
        n = MART_DATE_SLACK_DAYS_DEFAULT
    now_delta = f"+{n} days"
    return _safe_scalar_sql_params(
        conn,
        f"""
        SELECT MAX({column}) FROM {table}
        WHERE {column} IS NOT NULL AND trim({column}) != ''
          AND (
            date({column}) IS NULL
            OR date({column}) <= date('now', ?)
          )
        """,
        (now_delta,),
    )


def _date_prefix_for_compare(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return v[:10]
    return None


def _days_since_iso_prefix(prefix: str | None) -> int | None:
    if not prefix or len(prefix) < 10:
        return None
    try:
        y, m, d = int(prefix[:4]), int(prefix[5:7]), int(prefix[8:10])
        end = date(y, m, d)
        return (date.today() - end).days
    except ValueError:
        return None


class EmailDateHealthSnapshot(NamedTuple):
    """Read-only stats for emails.date_iso (raw vs future-filtered)."""

    raw_min: str | None
    raw_max: str | None
    future_dated_count: int
    max_future_date_iso: str | None
    plausible_max_date_iso: str | None
    slack_days: int


def load_email_date_health(
    conn: sqlite3.Connection,
    *,
    slack_days: int = MART_DATE_SLACK_DAYS_DEFAULT,
    emails_extra_where: str | None = None,
) -> EmailDateHealthSnapshot:
    """Detect future-dated rows via SQLite date() and max plausible MAX(date_iso).

    Suspicious: date(date_iso) > date('now', '+N days'). Rows where date() is NULL are
    not counted as future (may be malformed — see doc). Plausible max includes rows
    where date() IS NULL OR date() <= threshold (so unparseable strings can still
    affect MAX lexicographically — narrow edge case).

    ``emails_extra_where`` must be a **trusted** SQL boolean fragment (typically from
    :func:`origenlab_email_pipeline.contacto_gmail_source.sql_predicate_contacto_gmail_source`)
    ANDed into each query; never pass user input.
    """
    n = slack_days
    if n < 0 or n > 3660:
        n = MART_DATE_SLACK_DAYS_DEFAULT
    now_delta = f"+{n} days"
    ew = f" AND ({emails_extra_where})" if emails_extra_where else ""

    raw_min = _safe_scalar_sql(
        conn,
        f"SELECT MIN(date_iso) FROM emails WHERE date_iso IS NOT NULL AND trim(date_iso) != ''{ew}",
    )
    raw_max = _safe_scalar_sql(
        conn,
        f"SELECT MAX(date_iso) FROM emails WHERE date_iso IS NOT NULL AND trim(date_iso) != ''{ew}",
    )

    future_dated_count = 0
    max_future_date_iso: str | None = None
    plausible_max_date_iso: str | None = None

    try:
        row_fc = conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE date_iso IS NOT NULL AND trim(date_iso) != ''
              {ew}
              AND date(date_iso) > date('now', ?)
            """,
            (now_delta,),
        ).fetchone()
        if row_fc:
            future_dated_count = int(row_fc[0])
    except sqlite3.Error:
        future_dated_count = -1  # signal SQL failure

    try:
        row_mf = conn.execute(
            f"""
            SELECT MAX(date_iso) FROM emails
            WHERE date_iso IS NOT NULL AND trim(date_iso) != ''
              {ew}
              AND date(date_iso) > date('now', ?)
            """,
            (now_delta,),
        ).fetchone()
        if row_mf and row_mf[0] is not None:
            mf = str(row_mf[0]).strip()
            max_future_date_iso = mf if mf else None
        else:
            max_future_date_iso = None
    except sqlite3.Error:
        max_future_date_iso = None

    try:
        row_pm = conn.execute(
            f"""
            SELECT MAX(date_iso) FROM emails
            WHERE date_iso IS NOT NULL AND trim(date_iso) != ''
              {ew}
              AND (
                date(date_iso) IS NULL
                OR date(date_iso) <= date('now', ?)
              )
            """,
            (now_delta,),
        ).fetchone()
        if row_pm and row_pm[0] is not None:
            pm = str(row_pm[0]).strip()
            plausible_max_date_iso = pm if pm else None
        else:
            plausible_max_date_iso = None
    except sqlite3.Error:
        plausible_max_date_iso = None

    if future_dated_count < 0:
        future_dated_count = 0

    return EmailDateHealthSnapshot(
        raw_min=raw_min,
        raw_max=raw_max,
        future_dated_count=future_dated_count,
        max_future_date_iso=max_future_date_iso,
        plausible_max_date_iso=plausible_max_date_iso,
        slack_days=n,
    )


def render_data_health_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Read-only snapshot: DB path, counts, date span, sources, mart vs raw hints."""
    st.subheader("Salud de datos y vigencia")
    render_page_status("Salud de datos")
    st.caption(
        "Vista técnica: el archivo SQLite mostrado es el que ve esta app. "
        "No sustituye registros de ingest ni ejecuta reconstrucción del mart."
    )
    st.markdown(f"**Ruta SQLite:** `{db_path}`")
    st.info(
        "**Fuente operativa:** correo **Google Workspace** ingerido como "
        "`gmail:contacto@origenlab.cl/...` (ver `docs/ingest/WORKSPACE_GMAIL_IMAP.md`).\n\n"
        "**Histórico / referencia:** exportaciones **mbox** de `contacto@labdelivery.cl` y otros "
        "PST/mbox viven en la misma tabla `emails`, pero **no** equivalen al buzón vivo de OrigenLab "
        "para vigencia operativa, colas de casos ni memoria anti‑repetición basada en Gmail."
    )

    if not _has_table(conn, "emails"):
        st.error("No existe la tabla `emails` en este archivo.")
        return

    counts = {
        "emails": _safe_count(conn, "emails"),
        "attachments": _safe_count(conn, "attachments"),
        "attachment_extracts": _safe_count(conn, "attachment_extracts"),
        "contact_master": _safe_count(conn, "contact_master"),
        "organization_master": _safe_count(conn, "organization_master"),
        "document_master": _safe_count(conn, "document_master"),
        "opportunity_signals": _safe_count(conn, "opportunity_signals"),
    }
    count_rows = [{"tabla": k, "filas": counts[k] if counts[k] is not None else "— (sin tabla)"} for k in counts]
    st.markdown("#### Conteos principales")
    st.dataframe(pd.DataFrame(count_rows), use_container_width=True, hide_index=True)

    _gmail_pred = sql_predicate_contacto_gmail_source()
    n_labdelivery = int(
        conn.execute(
            "SELECT COUNT(*) FROM emails WHERE lower(source_file) LIKE '%contacto@labdelivery%'"
        ).fetchone()[0]
    )
    n_gmail_c_pre = int(
        conn.execute(f"SELECT COUNT(*) FROM emails WHERE {_gmail_pred}").fetchone()[0]
    )
    st.caption(
        f"Filas **legacy** `contacto@labdelivery` (mbox): **{n_labdelivery:,}**. "
        f"Filas **Gmail Workspace operativo** (`{_gmail_pred}`): **{n_gmail_c_pre:,}**."
    )

    edh_full = load_email_date_health(conn, slack_days=2)
    edh_canon = load_email_date_health(conn, slack_days=2, emails_extra_where=_gmail_pred)

    st.markdown("#### Archivo crudo — **todos los orígenes** (`emails.date_iso`)")
    st.write(
        {
            "min(date_iso)": edh_full.raw_min or "—",
            "max(date_iso) (absoluto)": edh_full.raw_max or "—",
            "max(date_iso) plausible": edh_full.plausible_max_date_iso or "—",
            "filas con fecha futura sospechosa": edh_full.future_dated_count,
            "umbral (días sobre hoy)": edh_full.slack_days,
        }
    )
    st.markdown("#### Fuente operativa — **solo Gmail Workspace** (`gmail:contacto@origenlab.cl/…`)")
    st.write(
        {
            "min(date_iso)": edh_canon.raw_min or "—",
            "max(date_iso) (absoluto)": edh_canon.raw_max or "—",
            "max(date_iso) plausible": edh_canon.plausible_max_date_iso or "—",
            "filas con fecha futura sospechosa": edh_canon.future_dated_count,
            "umbral (días sobre hoy)": edh_canon.slack_days,
        }
    )
    if edh_full.future_dated_count > 0:
        st.warning(
            f"Se detectaron **{edh_full.future_dated_count}** filas (archivo completo) donde `date(date_iso)` supera "
            f"hoy + **{edh_full.slack_days}** días (posible dato corrupto o cabecera incorrecta). "
            f"Máximo entre ellas: `{edh_full.max_future_date_iso or '—'}`. "
            "**La vigencia operativa** (abajo) usa el máximo plausible **del Gmail Workspace** cuando hay filas "
            "`gmail:contacto@origenlab.cl/…`; si no hay, cae al archivo completo."
        )
    st.caption(
        "El máximo plausible excluye filas cuya fecha calendario (según SQLite `date(date_iso)`) "
        "está más de {n} días en el futuro; las filas con `date_iso` no parseable por SQLite "
        "siguen pudiendo entrar en ese máximo. Ver documentación.".format(n=edh_full.slack_days)
    )

    edh_for_vigencia = edh_canon if n_gmail_c_pre > 0 else edh_full
    if edh_for_vigencia.plausible_max_date_iso:
        raw_prefix_for_vigencia = _date_prefix_for_compare(edh_for_vigencia.plausible_max_date_iso)
    elif edh_for_vigencia.future_dated_count == 0:
        raw_prefix_for_vigencia = _date_prefix_for_compare(edh_for_vigencia.raw_max)
    else:
        raw_prefix_for_vigencia = None
        st.warning(
            "No hay **máximo plausible** calculable (p. ej. todas las fechas parseables están en el futuro). "
            "La vigencia frente al mart quedará en **desconocida** hasta corregir fechas o el ingest."
        )
    days_old = _days_since_iso_prefix(raw_prefix_for_vigencia)
    if days_old is not None and days_old > 90:
        st.warning(
            f"Según la fecha máxima **plausible**, el último correo parece tener **~{days_old} días** "
            "de antigüedad (umbral 90 días). Verifique ingest si esperaba correo reciente."
        )

    st.markdown("#### Origen (`source_file`)")
    try:
        src_df = _load_df(
            conn,
            """
            SELECT source_file, COUNT(*) AS n
            FROM emails
            GROUP BY source_file
            ORDER BY n DESC
            LIMIT 40
            """,
        )
        if src_df.empty:
            st.info("No hay filas en `emails`.")
        else:
            st.dataframe(src_df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"No se pudo agrupar por source_file: {exc}")

    n_gmail_c = n_gmail_c_pre
    n_imap_c = (
        int(
            conn.execute(
                """
                SELECT COUNT(*) FROM emails
                WHERE lower(source_file) LIKE 'imap:contacto@origenlab.cl%'
                """
            ).fetchone()[0]
        )
        if _has_table(conn, "emails")
        else 0
    )
    st.write(
        {
            "gmail:contacto@origenlab.cl/… (operativo)": n_gmail_c,
            "imap:contacto@origenlab.cl*": n_imap_c,
        }
    )
    if (n_gmail_c + n_imap_c) == 0 and (counts.get("emails") or 0) > 0:
        st.warning(
            "No se detectaron filas con `source_file` típico de **Gmail Workspace** "
            "(`gmail:contacto@...`) ni **Titan IMAP** (`imap:contacto@...`). "
            "Si el buzón debería estar en este archivo, revise ingest y prefijos reales arriba."
        )

    st.markdown("#### Mart vs archivo crudo (heurística)")
    slack_mart = edh_for_vigencia.slack_days
    contact_mx = None
    contact_mx_plausible = None
    org_mx = None
    org_mx_plausible = None
    doc_mx = None
    doc_mx_plausible = None
    opp_mx = None
    if _has_table(conn, "contact_master"):
        contact_mx = _safe_scalar_sql(conn, "SELECT MAX(last_seen_at) FROM contact_master")
        contact_mx_plausible = _mart_plausible_max_ts(
            conn, "contact_master", "last_seen_at", slack_mart
        )
    if _has_table(conn, "organization_master"):
        org_mx = _safe_scalar_sql(conn, "SELECT MAX(last_seen_at) FROM organization_master")
        org_mx_plausible = _mart_plausible_max_ts(
            conn, "organization_master", "last_seen_at", slack_mart
        )
    if _has_table(conn, "document_master"):
        doc_mx = _safe_scalar_sql(conn, "SELECT MAX(sent_at) FROM document_master")
        doc_mx_plausible = _mart_plausible_max_ts(conn, "document_master", "sent_at", slack_mart)
    if _has_table(conn, "opportunity_signals"):
        opp_mx = _safe_scalar_sql(conn, "SELECT MAX(created_at) FROM opportunity_signals")

    mart_candidates: list[str] = []
    for val in (contact_mx_plausible, org_mx_plausible, doc_mx_plausible):
        p = _date_prefix_for_compare(val)
        if p:
            mart_candidates.append(p)
    mart_peak = max(mart_candidates) if mart_candidates else None
    raw_p = raw_prefix_for_vigencia

    vigencia_basis = (
        "Gmail Workspace `gmail:contacto@origenlab.cl/…`"
        if n_gmail_c > 0
        else "todos los orígenes (sin filas `gmail:contacto@origenlab.cl/…`)"
    )

    verdict = "unknown"
    verdict_detail = ""
    if raw_p and mart_peak:
        if mart_peak < raw_p:
            verdict = "stale"
            verdict_detail = (
                f"El máximo **plausible** contact/org/document en mart ({mart_peak}) es **anterior** al último "
                f"`date_iso` plausible comparado ({raw_p}; **{vigencia_basis}**). Conviene "
                f"`uv run python scripts/mart/build_business_mart.py --rebuild` tras ingest. (Los picos absolutos del "
                f"mart pueden seguir mostrando fechas imposibles hasta reconstruir.)"
            )
        else:
            verdict = "fresh"
            verdict_detail = (
                f"Picos **plausibles** de contact/org/document en el mart ({mart_peak}) alcanzan o superan el último "
                f"`date_iso` **plausible** comparado ({raw_p}; **{vigencia_basis}**) (prefijo YYYY-MM-DD). "
                f"No se usa `opportunity_signals.created_at` aquí: es **hora de regeneración del mart**, no del hecho."
            )
    elif not raw_p:
        verdict = "unknown"
        verdict_detail = "No hay `date_iso` útil en `emails` (ni plausible ni absoluto) para comparar."
    elif not mart_peak:
        verdict = "unknown"
        verdict_detail = "No hay fechas en tablas del mart para comparar (mart vacío o sin fechas)."

    st.write(
        {
            "contact_master.max(last_seen_at) absoluto": contact_mx or "—",
            "contact_master.max(...) plausible (≤ hoy+umbral)": contact_mx_plausible or "—",
            "organization_master.max(last_seen_at) absoluto": org_mx or "—",
            "organization_master.max(...) plausible": org_mx_plausible or "—",
            "document_master.max(sent_at) absoluto": doc_mx or "—",
            "document_master.max(sent_at) plausible": doc_mx_plausible or "—",
            "opportunity_signals.max(created_at) (regeneración mart)": opp_mx or "—",
            "mart_peak para vigencia (solo contact/org/doc plausible)": mart_peak or "—",
            "prefijo fecha crudo usado en vigencia (plausible si existe)": raw_p or "—",
            "base de comparación (operativa vs archivo completo)": vigencia_basis,
            "juicio_mart_vs_raw": verdict,
        }
    )
    st.caption(
        "Tras **reconstruir el mart** (`build_business_mart --rebuild`), "
        "`last_seen_at` / `sent_at` ignoran correos cuya fecha parseable queda más allá del umbral "
        f"(mismo criterio que arriba: **{slack_mart}** días sobre hoy). El archivo crudo no se modifica. "
        "`opportunity_signals.created_at` es cuando se **volvieron a escribir** las filas heurísticas, "
        "no la hora del correo ni del «descubrimiento» comercial."
    )
    if verdict == "stale":
        st.error(verdict_detail)
    elif verdict == "fresh":
        st.success(verdict_detail)
    else:
        st.info(verdict_detail)

    st.markdown("#### Metadatos de pipeline (si existen)")
    if _has_table(conn, "pipeline_kv"):
        try:
            kv_df = _load_df(
                conn,
                """
                SELECT k, v, updated_at
                FROM pipeline_kv
                ORDER BY updated_at DESC
                LIMIT 20
                """,
            )
            st.dataframe(kv_df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"pipeline_kv: {exc}")
    else:
        st.caption("Tabla `pipeline_kv` no presente.")

    if _has_table(conn, "pipeline_run"):
        try:
            run_df = _load_df(
                conn,
                """
                SELECT id, started_at, finished_at, script_name, notes
                FROM pipeline_run
                WHERE script_name LIKE '%build_business_mart%'
                ORDER BY id DESC
                LIMIT 5
                """,
            )
            st.markdown("Últimas ejecuciones registradas de **build_business_mart**:")
            if run_df.empty:
                st.caption("Sin filas que coincidan.")
            else:
                st.dataframe(run_df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"pipeline_run: {exc}")
    else:
        st.caption("Tabla `pipeline_run` no presente.")

    st.markdown("---")
    st.caption(
        "Interpretación y límites: `apps/email-pipeline/docs/pipeline/STREAMLIT_DATA_FRESHNESS.md`."
    )


def _where_contacto_gmail_source(*, table_alias: str | None = None) -> str:
    """SQL fragment: lower(<alias>.source_file) LIKE contacto Gmail Workspace pattern."""
    return sql_predicate_contacto_gmail_source(table_alias=table_alias, coalesce_null=False)


def _contacto_gmail_upper_slack(slack_days: int = 2) -> str:
    n = slack_days if 0 <= slack_days <= 3660 else 2
    return f"+{n} days"


class ContactoGmailActivitySummary(NamedTuple):
    total_rows: int
    count_7d: int
    count_30d: int
    count_90d: int
    most_recent_plausible_iso: str | None


def load_contacto_gmail_activity_summary(
    conn: sqlite3.Connection,
    *,
    slack_days: int = 2,
) -> ContactoGmailActivitySummary:
    """Counts for Gmail-ingested contacto@origenlab.cl rows; windows use SQLite date()."""
    w = _where_contacto_gmail_source()
    upper = _contacto_gmail_upper_slack(slack_days)
    try:
        total = int(conn.execute(f"SELECT COUNT(*) FROM emails WHERE {w}").fetchone()[0])
    except sqlite3.Error:
        total = 0

    def _window_count(days: int) -> int:
        try:
            row = conn.execute(
                f"""
                SELECT COUNT(*) FROM emails
                WHERE {w}
                  AND date_iso IS NOT NULL AND trim(date_iso) != ''
                  AND date(date_iso) >= date('now', ?)
                  AND date(date_iso) <= date('now', ?)
                """,
                (f"-{days} days", upper),
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    mr: str | None = None
    try:
        row_mr = conn.execute(
            f"""
            SELECT MAX(date_iso) FROM emails
            WHERE {w}
              AND date_iso IS NOT NULL AND trim(date_iso) != ''
              AND (date(date_iso) IS NULL OR date(date_iso) <= date('now', ?))
            """,
            (upper,),
        ).fetchone()
        if row_mr and row_mr[0] is not None:
            s = str(row_mr[0]).strip()
            mr = s if s else None
    except sqlite3.Error:
        mr = None

    return ContactoGmailActivitySummary(
        total_rows=total,
        count_7d=_window_count(7),
        count_30d=_window_count(30),
        count_90d=_window_count(90),
        most_recent_plausible_iso=mr,
    )


def load_contacto_gmail_recent_emails_df(conn: sqlite3.Connection, *, limit: int = 50) -> pd.DataFrame:
    w = _where_contacto_gmail_source()
    lim = max(1, min(int(limit), 500))
    try:
        return _load_df(
            conn,
            f"""
            SELECT
              date_iso,
              substr(COALESCE(subject, ''), 1, 120) AS subject_preview,
              substr(COALESCE(sender, ''), 1, 120) AS sender_preview,
              source_file
            FROM emails
            WHERE {w}
            ORDER BY
              CASE WHEN date_iso IS NULL OR trim(date_iso) = '' THEN 1 ELSE 0 END,
              date_iso DESC
            LIMIT ?
            """,
            (lim,),
        )
    except Exception:
        return pd.DataFrame()


def load_contacto_gmail_recent_documents_df(conn: sqlite3.Connection, *, limit: int = 25) -> pd.DataFrame:
    if not _has_table(conn, "document_master"):
        return pd.DataFrame()
    w = _where_contacto_gmail_source(table_alias="e")
    lim = max(1, min(int(limit), 200))
    try:
        return _load_df(
            conn,
            f"""
            SELECT
              d.sent_at,
              substr(COALESCE(d.filename, ''), 1, 80) AS filename_preview,
              d.doc_type,
              d.sender_domain,
              d.email_id
            FROM document_master d
            JOIN emails e ON e.id = d.email_id
            WHERE {w}
            ORDER BY
              CASE WHEN d.sent_at IS NULL OR trim(d.sent_at) = '' THEN 1 ELSE 0 END,
              d.sent_at DESC
            LIMIT ?
            """,
            (lim,),
        )
    except Exception:
        return pd.DataFrame()


def load_contacto_gmail_recent_signals_df(conn: sqlite3.Connection, *, limit: int = 25) -> pd.DataFrame:
    if not _has_table(conn, "opportunity_signals"):
        return pd.DataFrame()
    w = _where_contacto_gmail_source(table_alias="e")
    lim = max(1, min(int(limit), 200))
    try:
        return _load_df(
            conn,
            f"""
            SELECT
              s.created_at,
              s.signal_type,
              s.entity_kind,
              substr(COALESCE(s.entity_key, ''), 1, 80) AS entity_key_preview,
              s.score,
              s.email_id
            FROM opportunity_signals s
            JOIN emails e ON e.id = s.email_id
            WHERE {w}
            ORDER BY
              CASE WHEN s.created_at IS NULL OR trim(s.created_at) = '' THEN 1 ELSE 0 END,
              s.created_at DESC
            LIMIT ?
            """,
            (lim,),
        )
    except Exception:
        return pd.DataFrame()


BRAND = {
    "50": "#f0fdfa",
    "500": "#14b8a6",
    "600": "#0d9488",
    "700": "#0f766e",
    "800": "#115e59",
    "900": "#134e4a",
    "950": "#042f2e",
}


def _render_copy_email_button(email: str, *, key: str, label: str = "Copiar") -> None:
    value = (email or "").strip()
    if not value:
        return
    safe_email = json.dumps(value)
    safe_key = "".join(ch if ch.isalnum() else "_" for ch in key)
    safe_label = json.dumps(label)
    html = f"""
    <button id="copy_btn_{safe_key}" style="
      width: 100%;
      padding: 0.35rem 0.6rem;
      border: 1px solid #cbd5e1;
      border-radius: 0.5rem;
      background: white;
      cursor: pointer;
      font-size: 0.9rem;
    ">{label}</button>
    <script>
    const btn = document.getElementById("copy_btn_{safe_key}");
    if (btn) {{
      btn.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText({safe_email});
          btn.textContent = "Copiado";
          setTimeout(() => btn.textContent = JSON.parse({safe_label}), 1200);
        }} catch (e) {{
          btn.textContent = "No se pudo copiar";
        }}
      }});
    }}
    </script>
    """
    components.html(html, height=40)


def _render_copyable_email_row(email: str, *, key: str, prefix: str = "Email") -> None:
    value = (email or "").strip()
    if not value:
        return
    c1, c2 = st.columns([6, 1])
    with c1:
        st.markdown(f"**{prefix}:** `{value}`")
    with c2:
        _render_copy_email_button(value, key=key)


def _ensure_contact_email_suppression_ddl(db_path: Path) -> bool:
    try:
        conn_rw = sqlite3.connect(str(db_path), timeout=60.0)
    except sqlite3.Error:
        return False
    try:
        ensure_contact_email_suppression_table(conn_rw)
        conn_rw.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn_rw.close()


EQUIPMENT_INFO: dict[str, dict[str, str]] = {
    "autoclave": {
        "label": "Autoclave",
        "description": "Equipo de esterilización por vapor a alta presión y temperatura para material de laboratorio y residuos biológicos.",
    },
    "balanza": {
        "label": "Balanza",
        "description": "Equipo para pesar muestras con precisión (analítica, semi-micro, etc.).",
    },
    "osmometro": {
        "label": "Osmómetro",
        "description": "Equipo para medir la osmolaridad/osmolalidad de soluciones o muestras biológicas y de laboratorio.",
    },
    "termobalanza": {
        "label": "Termobalanza",
        "description": "Equipo termoanalítico para determinaciones por pérdida de masa/variación con temperatura (p. ej., TGA/termo-gravimetría).",
    },
    "centrifuga": {
        "label": "Centrífuga",
        "description": "Equipo que separa componentes de una muestra por fuerza centrífuga (rpm / RCF).",
    },
    "cromatografia_hplc": {
        "label": "Cromatografía HPLC",
        "description": "Sistema de cromatografía líquida de alta resolución para análisis cuantitativo de compuestos.",
    },
    "espectrofotometro": {
        "label": "Espectrofotómetro",
        "description": "Equipo que mide absorbancia/transmitancia de luz a distintas longitudes de onda.",
    },
    "horno_mufla": {
        "label": "Horno mufla",
        "description": "Horno de alta temperatura para calcinación, pérdida por ignición y otros ensayos térmicos.",
    },
    "humedad_granos": {
        "label": "Medidor de humedad",
        "description": "Equipo para determinar el porcentaje de humedad en granos y otros materiales (según el contexto del texto).",
    },
    "incubadora": {
        "label": "Incubadora",
        "description": "Cámara controlada de temperatura (y a veces CO₂/humedad) para cultivo de microorganismos y células.",
    },
    "liofilizador": {
        "label": "Liofilizador",
        "description": "Equipo para secado por congelación (freeze-drying) de muestras sensibles.",
    },
    "microscopio": {
        "label": "Microscopio",
        "description": "Equipo óptico para observación ampliada de muestras (biológicas o materiales).",
    },
    "phmetro": {
        "label": "pH-metro",
        "description": "Instrumento para medir de forma precisa el pH de soluciones acuosas.",
    },
    "pipetas": {
        "label": "Pipetas",
        "description": "Pipetas y micropipetas para dispensar volúmenes conocidos de líquido con precisión.",
    },
    "titulador": {
        "label": "Titulador",
        "description": "Equipo (manual o automático) para realizar titulaciones y determinar concentraciones de analitos.",
    },
    "sonicador": {
        "label": "Sonicador / ultrasonido",
        "description": "Equipo de ultrasonido para dispersar muestras, romper células o limpiar piezas por cavitación.",
    },
}


def _navigate_to(page: str, **flags: object) -> None:
    """Delegación al contrato centralizado (misma semántica que antes)."""
    navigate_to_page(page, **flags)


def _friendly_org_type(code: str | None) -> str:
    if not code:
        return "Sin clasificar"
    mapping = {
        "education": "Educación (universidad/centro académico)",
        "business": "Empresa",
        "gov": "Gobierno",
        "personal": "Email personal / otro",
    }
    return mapping.get(code, "Otro tipo de organización")


def _friendly_doc_type(code: str | None) -> str:
    if not code:
        return "Documento sin clasificar"
    mapping = {
        "quote": "Cotización",
        "invoice": "Factura",
        "price_list": "Lista de precios",
        "purchase_order": "Orden de compra",
    }
    return mapping.get(code, "Otro documento")


def _signal_label(signal_type: str) -> tuple[str, str]:
    m = {
        "quote_email_plus_quote_doc": (
            "Cotización + documento",
            "Contacto con correos de cotización repetidos y al menos un documento tipo cotización extraído.",
        ),
        "education_with_quote_activity": (
            "Universidad con cotización",
            "Organización tipo educación con actividad de cotización (correo o documento).",
        ),
        "dormant_contact": (
            "Cuenta dormida",
            "Contacto con alto historial, pero sin actividad reciente (heurístico).",
        ),
        "repeated_equipment_theme": (
            "Tema de equipo recurrente",
            "Contacto que menciona repetidamente el mismo equipo (tag) en asunto/cuerpo/documentos.",
        ),
    }
    return m.get(signal_type, (signal_type, "Señal heurística (ver detalles)."))


def render_contacto_gmail_activity_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Read-only recent activity for Gmail-ingested contacto@origenlab.cl mailbox."""
    st.subheader("Actividad reciente (contacto Gmail)")
    render_page_status("Actividad contacto Gmail")
    st.caption(
        "**Fuente operativa:** Google Workspace ingerido como `gmail:contacto@origenlab.cl/…` "
        "(no equivale a exportaciones mbox de `contacto@labdelivery.cl`; esas siguen en **Salud de datos** "
        "como histórico). No incluye buzón Titan (`imap:contacto@…`) salvo que comparta el mismo prefijo."
    )
    if not _has_table(conn, "emails"):
        st.error("No existe la tabla `emails` en este archivo.")
        return

    summary = load_contacto_gmail_activity_summary(conn, slack_days=2)
    if summary.total_rows == 0:
        st.warning(
            "No hay filas con origen **`gmail:contacto@origenlab.cl`** en `emails`. "
            "Si el correo operativo está en **Titan IMAP**, es normal; use la tabla de orígenes en **Salud de datos** "
            "o ejecute `05_workspace_gmail_imap_to_sqlite.py` tras configurar OAuth (ver `docs/ingest/WORKSPACE_GMAIL_IMAP.md`)."
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_metric("Mensajes contacto Gmail (total)", f"{summary.total_rows:,}")
    with c2:
        render_kpi_metric("Últimos 7 días", f"{summary.count_7d:,}", help_text="date_iso parseable por SQLite en ventana.")
    with c3:
        render_kpi_metric("Últimos 30 días", f"{summary.count_30d:,}")
    with c4:
        render_kpi_metric("Últimos 90 días", f"{summary.count_90d:,}")
    st.markdown(
        f"**Última fecha plausible (`date_iso`):** `{summary.most_recent_plausible_iso or '—'}` "
        "(excluye fechas > hoy + 2 días en calendario SQLite)."
    )

    st.markdown("#### Correos recientes (contacto Gmail)")
    emails_df = load_contacto_gmail_recent_emails_df(conn, limit=50)
    if emails_df.empty:
        st.caption("Sin filas para mostrar.")
    else:
        st.dataframe(emails_df, use_container_width=True, hide_index=True)

    docs_df = load_contacto_gmail_recent_documents_df(conn, limit=25)
    if _has_table(conn, "document_master"):
        st.markdown("#### Documentos recientes (correos contacto Gmail)")
        if docs_df.empty:
            st.caption("Sin documentos asociados a estos `email_id` o mart no construido.")
        else:
            docs_show = docs_df.copy()
            docs_show["doc_type"] = docs_show["doc_type"].apply(
                lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
            )
            st.dataframe(
                docs_show.rename(
                    columns={
                        "sent_at": "Enviado",
                        "filename_preview": "Archivo",
                        "doc_type": "Tipo",
                        "sender_domain": "Dominio remitente",
                        "email_id": "email_id",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    sig_df = load_contacto_gmail_recent_signals_df(conn, limit=25)
    if _has_table(conn, "opportunity_signals"):
        st.markdown("#### Señales recientes ligadas a esos correos")
        st.caption(
            "La columna **Mart (regenerado)** es el instante en que se regeneró la fila en "
            "`opportunity_signals` al ejecutar `build_business_mart`, no la fecha del hecho ni del correo."
        )
        if sig_df.empty:
            st.caption("Sin señales con `email_id` unido a contacto Gmail (o mart/señales vacíos).")
        else:
            sig_display = sig_df.copy()
            sig_display["señal"] = sig_display["signal_type"].apply(lambda x: _signal_label(str(x))[0])
            st.dataframe(
                sig_display.rename(
                    columns={
                        "created_at": "Mart (regenerado)",
                        "entity_kind": "entidad",
                        "entity_key_preview": "Clave",
                        "score": "score",
                    }
                )[
                    [
                        "Mart (regenerado)",
                        "señal",
                        "entidad",
                        "Clave",
                        "score",
                        "email_id",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.caption(f"Archivo: `{db_path}` · Vista informativa (no es bandeja de entrada completa).")


def render_proveedores_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Catálogo de proveedores / abastecimiento importado (solo lectura)."""
    st.subheader("Proveedores")
    render_page_status("Proveedores")
    st.caption(
        "Abastecimiento y partners internacionales — fuente estructurada (workbook DeepSearch), "
        "independiente de `lead_master`. Solo lectura en esta versión."
    )
    ok, reason = supplier_browse_ready(conn)
    if not ok:
        st.warning(
            "En esta base **no hay** capa de proveedores (`supplier_master`). "
            "Importe el workbook con `uv run python scripts/import_supplier_workbook.py --xlsx <archivo.xlsx>`."
        )
        if reason:
            st.caption(f"Técnico: `{reason}` · `{db_path}`")
        return

    opts = supplier_browse_filter_options(conn)
    st.markdown("#### Filtros")
    r0, r1, r2 = st.columns(3)
    with r0:
        reg_pick = st.multiselect(
            "Región",
            options=opts["region"],
            default=[],
            key="sup_f_region",
        )
        tier_pick = st.multiselect(
            "Tier",
            options=opts["tier"],
            format_func=lambda x: {
                "top15": "Top 15 contacto",
                "top50": "Top 50 oportunidades",
                "anexo": "Anexo (sin duplicar)",
                "exclusion": "Exclusión histórica",
            }.get(str(x), str(x)),
            default=[],
            key="sup_f_tier",
        )
        min_conf = st.slider(
            "Confianza mín. (score)",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.05,
            key="sup_f_conf",
        )
    with r1:
        cat_sub = st.text_input("Foco / categoría (contiene)", "", key="sup_f_cat")
        ev_pick = st.radio(
            "Con evidencia URL",
            options=["any", "yes", "no"],
            format_func=lambda x: {"any": "Indiferente", "yes": "Sí", "no": "No"}[x],
            horizontal=True,
            key="sup_f_ev",
        )
        ch_pick = st.radio(
            "Canal de contacto",
            options=["any", "yes", "no"],
            format_func=lambda x: {"any": "Indiferente", "yes": "Con canal", "no": "Sin canal"}[x],
            horizontal=True,
            key="sup_f_ch",
        )
    with r2:
        st_pick = st.multiselect(
            "Estado revisión",
            options=opts["status"] or ["nuevo"],
            default=[],
            key="sup_f_st",
        )
        mb_pick = st.radio(
            "Archivo correo",
            options=["any", "yes", "no"],
            format_func=lambda x: {
                "any": "Indiferente",
                "yes": "Ya visto en correo",
                "no": "No en archivo",
            }[x],
            horizontal=True,
            key="sup_f_mb",
        )
        hide_excl = st.checkbox("Ocultar exclusiones históricas", value=True, key="sup_f_excl")
        row_cap = st.number_input(
            "Máx. filas",
            min_value=50,
            max_value=4000,
            value=1500,
            step=50,
            key="sup_f_lim",
        )

    flt = SupplierBrowseFilters(
        regions=tuple(reg_pick) if reg_pick else None,
        tiers=tuple(str(t) for t in tier_pick) if tier_pick else None,
        min_confidence=float(min_conf) if min_conf > 0 else None,
        category_substring=cat_sub.strip() or None,
        has_evidence=str(ev_pick),
        has_channel=str(ch_pick),
        statuses=tuple(st_pick) if st_pick else None,
        seen_in_mailbox=str(mb_pick),
        exclude_exclusions=hide_excl,
        limit=int(row_cap),
    )
    df = fetch_suppliers_browse_df(conn, flt, include_mailbox_join=True)
    if df.empty:
        st.info("No hay filas con estos filtros (o el último lote no tiene snapshots).")
        return
    display = df.rename(
        columns={
            "trade_name": "Proveedor",
            "domain_norm": "Dominio",
            "region_label": "Región",
            "country_label": "País",
            "equipment_focus": "Foco equipos",
            "tier": "Tier",
            "rank_in_list": "Ranking",
            "confidence_score": "Confianza",
            "confidence_label": "Confianza (texto)",
            "primary_channel": "Canal principal",
            "evidence_sample_url": "Evidencia (ejemplo)",
            "evidence_count": "Nº evidencias",
            "review_status": "Estado",
            "seen_in_mailbox": "En archivo correo",
        }
    )
    if "En archivo correo" in display.columns:
        display["En archivo correo"] = display["En archivo correo"].map(
            lambda v: "Sí" if int(v or 0) else "No"
        )
    show_cols = [
        c
        for c in [
            "Proveedor",
            "Dominio",
            "Región",
            "País",
            "Foco equipos",
            "Tier",
            "Ranking",
            "Confianza",
            "Confianza (texto)",
            "Canal principal",
            "Evidencia (ejemplo)",
            "Nº evidencias",
            "Estado",
            "En archivo correo",
        ]
        if c in display.columns
    ]
    st.dataframe(display[show_cols], use_container_width=True, hide_index=True)
    st.caption(f"Base de datos (solo lectura): `{db_path}`")


def _lead_research_status_label_es(code: str) -> str:
    return {
        "nuevo": "Nuevo",
        "investigar_contacto": "Investigar contacto",
        "contacto_encontrado": "Contacto encontrado",
        "listo_para_contacto": "Listo para contacto",
        "descartado": "Descartado",
    }.get(code, code)


def _render_lead_manual_enrichment_panel(conn: sqlite3.Connection, db_path: Path, df: pd.DataFrame) -> None:
    """Operator-owned contact research; optional RW via ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW=1."""
    if not _has_table(conn, "lead_contact_research"):
        st.info(
            "El enriquecimiento manual requiere la tabla `lead_contact_research`. "
            "Si acaba de ver una advertencia arriba, corrija el acceso de escritura al SQLite y recargue."
        )
        return

    st.markdown("### Enriquecimiento manual (revisión)")
    st.caption(
        "**No son datos de importación:** lo que guarde aquí queda en la tabla `lead_contact_research` y no modifica "
        "los campos crudos de `lead_master` (organización, correo, dominio de la fuente). Sirve para pasar de "
        "«licitación sin contacto» a «contacto localizado / listo» de forma explícita y auditable."
    )
    rw_ok = streamlit_leads_review_rw_enabled()
    if not rw_ok:
        st.info(
            "**Solo lectura:** puede ver el estado de investigación en la tabla de arriba (columnas «Investigación»). "
            "Para crear o editar registros desde esta app, use una base grabable y la variable de entorno "
            "`ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW=1` (misma filosofía que la revis comercial)."
        )

    try:
        pick_ids = [int(x) for x in df["lead_id"].tolist()]
    except (TypeError, ValueError, KeyError):
        pick_ids = []
    labels = []
    for _, r in df.iterrows():
        lid = int(r["lead_id"])
        org = str(r.get("org_name") or "")[:72]
        labels.append(f"{lid} — {org}" if org else str(lid))

    choice = st.selectbox(
        "Lead para ver o editar enriquecimiento",
        options=list(range(len(labels))),
        format_func=lambda i: labels[i] if labels else "—",
        key="leads_enrich_pick",
    )
    if not labels:
        return
    lead_id = pick_ids[choice]
    row_m = df[df["lead_id"] == lead_id].iloc[0]

    with st.expander("Datos provenientes del import (`lead_master`) — solo referencia", expanded=False):
        st.markdown(
            f"- **Organización:** {row_m.get('org_name') or '—'}\n"
            f"- **Contacto (fuente):** {row_m.get('contact_name') or '—'}\n"
            f"- **Correo (fuente):** {row_m.get('email') or '—'}\n"
            f"- **Dominio (fuente):** {row_m.get('source_domain') or '—'}\n"
            f"- **Sitio web (fuente):** {row_m.get('source_website') or '—'}\n"
        )
        st.caption("Si la fuente no trae contacto utilizable, use el bloque de enriquecimiento manual abajo.")

    cur = fetch_contact_research_row(conn, lead_id)

    if rw_ok:
        status_opts = list(CONTACT_RESEARCH_STATUSES)
        idx_cur = 0
        if cur and cur.get("contact_research_status") in status_opts:
            idx_cur = status_opts.index(str(cur["contact_research_status"]))

        with st.form("lead_contact_research_form", clear_on_submit=False):
            st.markdown("#### Editar enriquecimiento")
            st_status = st.selectbox(
                "Estado de investigación de contacto",
                options=status_opts,
                index=idx_cur,
                format_func=_lead_research_status_label_es,
                key="lcr_status",
            )
            st_domain = st.text_input(
                "Dominio resuelto (investigación)",
                value=str(cur["resolved_domain"] or "") if cur else "",
                key="lcr_domain",
                help="Se normaliza (minúsculas, sin www, sin rutas). No sustituye el dominio de importación.",
            )
            st_name = st.text_input(
                "Nombre de contacto resuelto",
                value=str(cur["resolved_contact_name"] or "") if cur else "",
                key="lcr_name",
            )
            st_email = st.text_input(
                "Correo resuelto",
                value=str(cur["resolved_contact_email"] or "") if cur else "",
                key="lcr_email",
            )
            st_src = st.text_input(
                "¿Origen de estos datos?",
                value=str(cur["contact_source"] or "") if cur else "",
                key="lcr_src",
                help="Ej.: sitio institucional, llamada, LinkedIn — queda guardado para auditoría.",
            )
            st_notes = st.text_area(
                "Notas de investigación",
                value=str(cur["contact_research_notes"] or "") if cur else "",
                key="lcr_notes",
                height=100,
            )
            st_by = st.text_input(
                "Quién actualiza (opcional, auditoría)",
                value=str(cur["updated_by"] or "") if cur else "",
                key="lcr_by",
            )

            submitted = st.form_submit_button("Guardar enriquecimiento")
            if submitted:
                conn_rw = sqlite3.connect(str(db_path), timeout=60.0)
                try:
                    ensure_leads_tables_ddl_base(conn_rw)
                    payload = validate_contact_research_payload(
                        contact_research_status=st_status,
                        resolved_domain=st_domain or None,
                        resolved_contact_name=st_name or None,
                        resolved_contact_email=st_email or None,
                        contact_source=st_src or None,
                        contact_research_notes=st_notes or None,
                        updated_by=st_by or None,
                    )
                    upsert_contact_research(conn_rw, lead_id=lead_id, payload=payload)
                    conn_rw.commit()
                    st.success("Guardado en `lead_contact_research` (datos de revisión, no de import).")
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
                finally:
                    conn_rw.close()

        if cur:
            if st.button("Quitar registro de enriquecimiento", key="lcr_delete"):
                conn_rw = sqlite3.connect(str(db_path), timeout=60.0)
                try:
                    ensure_leads_tables_ddl_base(conn_rw)
                    delete_contact_research(conn_rw, lead_id)
                    conn_rw.commit()
                    st.success("Registro de enriquecimiento eliminado.")
                    st.rerun()
                finally:
                    conn_rw.close()

        nd_raw = (st.session_state.get("lcr_domain") or "").strip()
        if nd_raw:
            from origenlab_email_pipeline.org_normalize import normalize_domain as _norm_dom

            dnorm = _norm_dom(nd_raw)
            if dnorm:
                name_guess, n_mail = archive_org_hint_for_domain(conn, dnorm)
                if name_guess:
                    st.caption(
                        f"Pista (solo informativa): el dominio **{dnorm}** coincide con `organization_master` "
                        f"({name_guess!r}, ~{n_mail!s} correos en mart). No se crea vínculo automático."
                    )
    else:
        if cur:
            st.markdown("#### Estado de enriquecimiento guardado")
        else:
            st.markdown("#### Sin registro de enriquecimiento")
        if cur:
            st.write(
                {
                    "Estado": _lead_research_status_label_es(str(cur["contact_research_status"])),
                    "Dominio resuelto": cur.get("resolved_domain") or "—",
                    "Contacto resuelto": cur.get("resolved_contact_name") or "—",
                    "Correo resuelto": cur.get("resolved_contact_email") or "—",
                    "Origen del dato": cur.get("contact_source") or "—",
                    "Notas": cur.get("contact_research_notes") or "—",
                    "Actualizado": cur.get("updated_at") or "—",
                    "Por": cur.get("updated_by") or "—",
                }
            )
            rd = cur.get("resolved_domain")
            if rd and isinstance(rd, str) and rd.strip():
                og, nm = archive_org_hint_for_domain(conn, rd.strip())
                if og:
                    st.caption(
                        f"Pista: dominio **{rd}** aparece en archivo (`organization_master`: {og!r}, correos≈{nm})."
                    )
        else:
            st.caption("Aún no hay fila en `lead_contact_research` para este lead.")


def render_leads_y_cuentas_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Leer `lead_master`, coincidencias con archivo, enriquecimiento opcional y rollup de cuentas."""
    st.subheader("Leads y cuentas")
    render_page_status(
        "Leads y cuentas",
        note=(
            "Si el modo RW está habilitado, el enriquecimiento manual se guarda en la base actual. Si no, esta vista queda en consulta."
        ),
    )
    _lb = st.session_state.pop(SESSION_LEADS_TODAY_BANNER, None)
    if _lb:
        st.info(_lb)
    st.caption(
        "Tabla principal: prospectos del pipeline externo (`lead_master`), prioridad, vínculos con el archivo "
        "y columnas de **enriquecimiento manual** cuando exista `lead_contact_research`. "
        "Los datos de import no se sobreescriben desde aquí."
    )


def _split_tags(value: object) -> list[str]:
    """Dividir un campo de tags heurísticos en una lista normalizada."""
    if value is None:
        return []
    text = str(value)
    if not text.strip():
        return []
    # Unificamos separadores comunes (coma / punto y coma / barra vertical).
    cleaned = text.replace(";", ",").replace("|", ",")
    tags: list[str] = []
    for raw in cleaned.split(","):
        t = raw.strip()
        if not t:
            continue
        # Normalización ligera de sinónimos, en particular ultrasonido → sonicador.
        low = t.lower()
        if "ultrason" in low or "ultra sonido" in low or "ultrasónico" in low or "ultrasonico" in low:
            tags.append("sonicador")
        else:
            tags.append(t)
    return tags


def _normalize_query(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _consume_nav_flag(key: str, default: bool = False) -> bool:
    """Consume one-shot navigation flags so quick-actions do not stick forever."""
    if key in st.session_state:
        return bool(st.session_state.pop(key))
    return default


def _search_relevance_score(df: pd.DataFrame, query: str, columns: list[str]) -> pd.Series:
    q = _normalize_query(query)
    if not q or df.empty:
        return pd.Series([0.0] * len(df), index=df.index)

    score = pd.Series([0.0] * len(df), index=df.index)
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col].fillna("").astype(str).str.lower()
        score += s.eq(q).astype(float) * 120.0
        score += s.str.startswith(q, na=False).astype(float) * 80.0
        score += s.str.contains(q, na=False).astype(float) * 30.0

    # Bonus when all tokens appear somewhere in searchable text.
    searchable = pd.Series([""] * len(df), index=df.index)
    for col in columns:
        if col in df.columns:
            searchable = searchable + " " + df[col].fillna("").astype(str).str.lower()
    for tok in [t for t in q.split(" ") if t]:
        score += searchable.str.contains(tok, na=False).astype(float) * 8.0
    return score


def _render_equipment_page(conn: sqlite3.Connection) -> None:
    """Dedicated equipment explorer (moved out of executive summary)."""
    st.subheader("Explorar por equipo")
    st.caption(
        "Seleccione un tipo de equipo para ver organizaciones, contactos, documentos y señales históricas "
        "relacionadas con ese tema."
    )

    tags: set[str] = set()
    org_tags_df = _load_df(
        conn,
        "SELECT DISTINCT top_equipment_tags FROM organization_master WHERE top_equipment_tags IS NOT NULL",
    )
    contact_tags_df = _load_df(
        conn,
        "SELECT DISTINCT top_equipment_tags FROM contact_master WHERE top_equipment_tags IS NOT NULL",
    )
    doc_tags_df = _load_df(
        conn,
        "SELECT DISTINCT equipment_tags FROM document_master WHERE equipment_tags IS NOT NULL",
    )
    for df_tags in (org_tags_df, contact_tags_df, doc_tags_df):
        for val in df_tags.iloc[:, 0].dropna():
            for t in _split_tags(val):
                tags.add(t)

    if not tags:
        st.info(
            "Por ahora no se detectan tags de equipos en el mart actual. "
            "Cuando existan, aquí se podrá explorar por equipo."
        )
        return

    preferred_order = [
        "autoclave",
        "balanza",
        "termobalanza",
        "osmometro",
        "centrifuga",
        "cromatografia_hplc",
        "espectrofotometro",
        "horno_mufla",
        "humedad_granos",
        "incubadora",
        "liofilizador",
        "microscopio",
        "phmetro",
        "pipetas",
        "titulador",
        "sonicador",
    ]
    preferred_in_data = [t for t in preferred_order if t in tags]
    remaining = sorted([t for t in tags if t not in preferred_in_data], key=lambda x: x.lower())
    ordered_tags = preferred_in_data + remaining

    display_to_tag: dict[str, str] = {}
    display_options: list[str] = []
    for tag in ordered_tags:
        info = EQUIPMENT_INFO.get(tag, {})
        label = info.get("label", tag)
        display = f"{label} ({tag})" if label != tag else label
        display_to_tag[display] = tag
        display_options.append(display)

    selected_display = st.selectbox("Seleccionar equipo o tema", options=display_options)
    selected_tag = display_to_tag[selected_display] if selected_display else ""
    if not selected_tag:
        return

    info = EQUIPMENT_INFO.get(selected_tag, {})
    label = info.get("label", selected_tag)
    st.markdown(f"Mostrando actividad histórica relacionada con **{label}**.")
    if desc := info.get("description"):
        st.caption(desc)

    suppress_noise = st.checkbox(
        "Ocultar ruido operacional/proveedor en tablas de equipo",
        value=True,
        help=(
            "Oculta dominios/plataformas transaccionales, organizaciones claramente ruido y "
            "dominios marcados como proveedor en supplier_master."
        ),
        key="equipment_hide_operational_noise",
    )
    supplier_domains = supplier_email_domains(conn) if suppress_noise else frozenset()

    st.markdown("#### Organizaciones relacionadas con este equipo")
    org_eq = _load_df(
        conn,
        """
        SELECT
          domain AS dominio,
          organization_name_guess AS organizacion,
          organization_type_guess AS tipo_org,
          first_seen_at AS primera,
          last_seen_at AS ultima,
          total_emails AS total,
          quote_email_count AS cotiz_email,
          invoice_email_count AS factura_email,
          purchase_email_count AS compra_email,
          business_doc_email_count AS doc_emails,
          top_equipment_tags AS equipos
        FROM organization_master
        """,
    )
    mask_org_eq = org_eq["equipos"].fillna("").str.contains(selected_tag, case=False, na=False)
    org_eq = org_eq[mask_org_eq]
    removed_org_noise = 0
    if suppress_noise and not org_eq.empty:
        org_domain = org_eq["dominio"].fillna("").astype(str).str.strip().str.lower()
        org_name = org_eq["organizacion"].fillna("").astype(str)
        org_noise_mask = org_domain.apply(
            lambda d: bool(d)
            and (
                marketing_outreach_noise_email(f"info@{d}", strict_contact_graph=True)
                or is_supplier_email_domain(f"info@{d}", supplier_domains)
            )
        ) | org_name.apply(marketing_outreach_noise_organization_guess)
        removed_org_noise = int(org_noise_mask.sum())
        org_eq = org_eq[~org_noise_mask]
    if org_eq.empty:
        st.info("No se encontraron organizaciones claramente asociadas a este equipo.")
    else:
        if suppress_noise and removed_org_noise > 0:
            st.caption(f"Se ocultaron {removed_org_noise} organizaciones de ruido operacional/proveedor.")
        org_eq_display = org_eq.copy()
        org_eq_display["tipo_org"] = org_eq_display["tipo_org"].apply(
            lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
        )
        org_eq_display = org_eq_display.rename(
            columns={
                "dominio": "Dominio",
                "organizacion": "Organización",
                "tipo_org": "Tipo de organización",
                "primera": "Primera actividad",
                "ultima": "Última actividad",
                "total": "Total de correos",
                "cotiz_email": "Correos con cotización",
                "factura_email": "Correos con factura",
                "compra_email": "Correos de compra/pedido",
                "doc_emails": "Correos con documentos comerciales",
                "equipos": "Equipos asociados (heurístico)",
            }
        )
        st.dataframe(org_eq_display.head(50), use_container_width=True, hide_index=True)

    st.markdown("#### Contactos relacionados con este equipo")
    contact_eq = _load_df(
        conn,
        """
        SELECT
          email,
          domain AS dominio,
          organization_name_guess AS organizacion,
          organization_type_guess AS tipo_org,
          first_seen_at AS primera,
          last_seen_at AS ultima,
          total_emails AS total,
          quote_email_count AS cotiz_email,
          invoice_email_count AS factura_email,
          business_doc_email_count AS doc_emails,
          top_equipment_tags AS equipos
        FROM contact_master
        """,
    )
    mask_contact_eq = contact_eq["equipos"].fillna("").str.contains(selected_tag, case=False, na=False)
    contact_eq = contact_eq[mask_contact_eq]
    removed_contact_noise = 0
    if suppress_noise and not contact_eq.empty:
        contact_email = contact_eq["email"].fillna("").astype(str).str.strip().str.lower()
        org_name = contact_eq["organizacion"].fillna("").astype(str)
        contact_noise_mask = contact_email.apply(
            lambda e: bool(e)
            and (
                marketing_outreach_noise_email(e, strict_contact_graph=True)
                or is_supplier_email_domain(e, supplier_domains)
            )
        ) | org_name.apply(marketing_outreach_noise_organization_guess)
        removed_contact_noise = int(contact_noise_mask.sum())
        contact_eq = contact_eq[~contact_noise_mask]
    if contact_eq.empty:
        st.info("No se encontraron contactos claramente asociados a este equipo.")
    else:
        if suppress_noise and removed_contact_noise > 0:
            st.caption(f"Se ocultaron {removed_contact_noise} contactos de ruido operacional/proveedor.")
        contact_eq_display = contact_eq.copy()
        contact_eq_display["tipo_org"] = contact_eq_display["tipo_org"].apply(
            lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
        )
        contact_eq_display = contact_eq_display.rename(
            columns={
                "email": "Contacto (email)",
                "dominio": "Dominio",
                "organizacion": "Organización",
                "tipo_org": "Tipo de organización",
                "primera": "Primera actividad",
                "ultima": "Última actividad",
                "total": "Total de correos",
                "cotiz_email": "Correos con cotización",
                "factura_email": "Correos con factura",
                "doc_emails": "Correos con documentos comerciales",
                "equipos": "Equipos asociados (heurístico)",
            }
        )
        st.dataframe(contact_eq_display.head(80), use_container_width=True, hide_index=True)

    st.markdown("#### Documentos comerciales relacionados con este equipo")
    doc_eq = _load_df(
        conn,
        """
        SELECT
          attachment_id,
          sent_at,
          doc_type,
          filename,
          sender_domain,
          equipment_tags
        FROM document_master
        """,
    )
    mask_doc_eq = doc_eq["equipment_tags"].fillna("").str.contains(selected_tag, case=False, na=False)
    doc_eq = doc_eq[mask_doc_eq]
    if doc_eq.empty:
        st.info("No se encontraron documentos explícitamente asociados a este equipo.")
    else:
        doc_eq_display = doc_eq.copy()
        doc_eq_display["doc_type"] = doc_eq_display["doc_type"].apply(
            lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
        )
        doc_eq_display = doc_eq_display.rename(
            columns={
                "sent_at": "Fecha envío",
                "doc_type": "Tipo de documento",
                "filename": "Archivo",
                "sender_domain": "Dominio remitente",
                "equipment_tags": "Equipos mencionados",
            }
        )
        st.dataframe(doc_eq_display.head(80), use_container_width=True, hide_index=True)

    st.markdown("#### Señales heurísticas relacionadas con este equipo")
    signals_eq = _load_df(
        conn,
        """
        SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
        FROM opportunity_signals
        WHERE details_json LIKE ?
        ORDER BY score DESC, created_at DESC
        """,
        (f"%{selected_tag}%",),
    )
    if signals_eq.empty:
        st.info(
            "No se encontraron señales heurísticas donde el detalle haga referencia explícita a este equipo."
        )
    else:
        signals_eq["señal"] = signals_eq["signal_type"].apply(lambda x: _signal_label(str(x))[0])
        signals_eq["explicación"] = signals_eq["signal_type"].apply(lambda x: _signal_label(str(x))[1])
        signals_display = signals_eq[
            ["señal", "explicación", "entity_kind", "entity_key", "score", "created_at"]
        ].copy()
        signals_display["Entidad"] = signals_display["entity_kind"].map(
            {"contact": "Contacto", "organization": "Organización"}
        ).fillna(signals_display["entity_kind"])
        signals_display = signals_display.rename(
            columns={
                "entity_key": "Clave (email/dominio)",
                "score": "Intensidad de la señal",
                "created_at": "Mart (regenerado)",
            }
        ).drop(columns=["entity_kind"])
        st.caption(
            "`Mart (regenerado)`: momento en que se regeneró la tabla `opportunity_signals` al reconstruir el mart; "
            "no es la fecha del correo ni del hallazgo comercial."
        )
        st.dataframe(signals_display.head(80), use_container_width=True, hide_index=True)
        with st.expander("Ver detalles técnicos de las señales por equipo"):
            st.dataframe(
                signals_eq[
                    ["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]
                ].head(200),
                use_container_width=True,
                hide_index=True,
            )


def main() -> None:
    st.set_page_config(page_title="OrigenLab — Base Comercial", layout="wide")
    st.title("OrigenLab — Base comercial")
    st.caption(
        "Señales y actividad histórica en correo/adjuntos. No implica ventas confirmadas ni facturación real."
    )

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()

    with st.expander("Fuente de datos (técnico)"):
        st.code(str(db_path))

    conn = _connect_ro(db_path)
    try:
        # Navegación por área + vista (mismas rutas; handoff vía ``SESSION_START_PAGE``).
        all_pages = _all_nav_pages()
        if SESSION_START_PAGE in st.session_state:
            _sp = st.session_state.pop(SESSION_START_PAGE)
            if _sp in all_pages:
                _gi = _nav_group_index_for_page(_sp)
                st.session_state["nav_area_ix"] = _gi
                if _sp in _NAV_GROUPS[_gi][1]:
                    st.session_state[f"nav_subpage_{_gi}"] = _sp

        st.markdown("##### Navegación")
        st.caption(
            "Elija un **área** y luego la **vista**. No hay pantallas nuevas: solo están agrupadas para orientarse más rápido."
        )
        _g_ix = st.selectbox(
            "Área",
            options=list(range(len(_NAV_GROUPS))),
            format_func=lambda i: _NAV_GROUPS[int(i)][0],
            label_visibility="collapsed",
            key="nav_area_ix",
        )
        if _NAV_GROUPS[int(_g_ix)][0] == PRIORIDAD_DEL_DIA_GROUP_TITLE:
            st.caption(PRIORIDAD_GROUP_NAV_CAPTION_ES)
        _plist = _NAV_GROUPS[int(_g_ix)][1]
        page = st.radio(
            "Vista",
            _plist,
            horizontal=True,
            label_visibility="collapsed",
            key=f"nav_subpage_{int(_g_ix)}",
        )
        if page not in all_pages:
            page = "Resumen"

        if page == "Salud de datos":
            render_data_health_page(conn, db_path)
            return

        if page == "Qué hacer hoy":
            render_que_hacer_hoy_page(conn, db_path)
            return

        if page == "Actividad contacto Gmail":
            render_contacto_gmail_activity_page(conn, db_path)
            return

        if page == "Casos para revisar":
            render_cases_to_review_page(conn, db_path)
            return

        if page == "Cola outreach marketing":
            render_next_marketing_queue_page(conn, db_path)
            return

        if page == "Borrador comercial":
            render_commercial_draft_review_page(conn, db_path)
            return

        if page == "Leads y cuentas":
            render_leads_y_cuentas_page(conn, db_path)
            return

        if page == "Proveedores":
            render_proveedores_page(conn, db_path)
            return

        required = ["contact_master", "organization_master", "document_master", "opportunity_signals"]
        missing = [t for t in required if not _has_table(conn, t)]
        if missing:
            st.error("Faltan tablas del mart: " + ", ".join(missing))
            st.info("Ejecute primero: `uv run python scripts/mart/build_business_mart.py --rebuild`")
            return

        if page == "Resumen":
            st.subheader("Resumen ejecutivo")
            render_page_status("Resumen")
            st.caption(
                "Panorama del archivo importado y del mart de negocio. Las tareas sugeridas del día están en **Qué hacer hoy**."
            )
            st.info(
                "**Fuente operativa OrigenLab:** correo **Google Workspace** (`gmail:contacto@origenlab.cl/…`). "
                "**Histórico / referencia:** exportaciones **mbox** (p. ej. `contacto@labdelivery.cl`) conviven en "
                "`emails`; el mart y los KPIs de archivo completo los incluyen — no los confunda con el buzón vivo."
            )
            total_msgs = int(_load_df(conn, "SELECT COUNT(*) AS c FROM emails").iloc[0]["c"])
            _op_pred = sql_predicate_contacto_gmail_source()
            op_msgs = int(_load_df(conn, f"SELECT COUNT(*) AS c FROM emails WHERE {_op_pred}").iloc[0]["c"])
            contacts_n = int(_load_df(conn, "SELECT COUNT(*) AS c FROM contact_master").iloc[0]["c"])
            orgs_n = int(_load_df(conn, "SELECT COUNT(*) AS c FROM organization_master").iloc[0]["c"])
            docs_n = int(_load_df(conn, "SELECT COUNT(*) AS c FROM document_master").iloc[0]["c"])
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                render_kpi_metric("Mensajes analizados", f"{total_msgs:,}")
            with c2:
                render_kpi_metric("Contactos externos", f"{contacts_n:,}")
            with c3:
                render_kpi_metric("Organizaciones externas", f"{orgs_n:,}")
            with c4:
                render_kpi_metric("Documentos útiles", f"{docs_n:,}")
            st.caption(
                f"Mensajes **operativos** (solo Gmail Workspace `gmail:contacto@origenlab.cl/…`): **{op_msgs:,}**."
            )

            # Periodo aproximado de cobertura del archivo de correo.
            try:
                period_df = _load_df(
                    conn,
                    "SELECT MIN(date_iso) AS primera, MAX(date_iso) AS ultima FROM emails WHERE date_iso IS NOT NULL",
                )
                primera = period_df.iloc[0]["primera"]
                ultima = period_df.iloc[0]["ultima"]
                if pd.notna(primera) and pd.notna(ultima):
                    primera_y = str(primera)[:4]
                    ultima_y = str(ultima)[:4]
                    st.caption(f"Periodo aproximado cubierto por el archivo: {primera_y}–{ultima_y}.")
            except Exception:
                # Si falla, no obstaculiza la navegación.
                pass

            st.markdown(
                "Esta base actúa como **memoria comercial histórica** basada en correos y adjuntos. "
                "No representa ventas confirmadas, sino señales e indicios de interés comercial."
            )

            st.divider()
            st.markdown("### Preguntas rápidas")
            qa_row1 = st.columns(3)

            with qa_row1[0]:
                st.markdown("**Universidades con cotización**")
                st.caption("Ver universidades con actividad de correos o documentos de cotización.")
                if st.button("Ir a organizaciones (universidades)", key="qa_unis_quotes"):
                    _navigate_to("Organizaciones", org_only_unis=True)

            with qa_row1[1]:
                st.markdown("**Clientes con muchas cotizaciones**")
                st.caption("Organizaciones con alto volumen de correos y documentos de cotización.")
                if st.button("Ver organizaciones con cotización", key="qa_org_quotes"):
                    _navigate_to("Organizaciones", org_focus_quotes=True)

            with qa_row1[2]:
                st.markdown("**Proveedores con facturas**")
                st.caption("Organizaciones con correos o documentos detectados como factura.")
                if st.button("Ver organizaciones con facturas", key="qa_org_invoices"):
                    _navigate_to("Organizaciones", org_only_invoices=True)

            qa_row2 = st.columns(3)

            with qa_row2[0]:
                st.markdown("**Cuentas dormidas valiosas**")
                st.caption("Contactos con mucho historial pero sin actividad reciente.")
                if st.button("Ver oportunidades de cuentas dormidas", key="qa_dormant_contacts"):
                    _navigate_to("Oportunidades", opp_signal_filter="dormant_contact")

            with qa_row2[1]:
                st.markdown("**Documentos de cotización recientes**")
                st.caption("Adjuntos clasificados como cotización en los últimos años.")
                if st.button("Ver documentos de cotización", key="qa_quote_docs"):
                    _navigate_to("Documentos", docs_only_quotes=True)

            with qa_row2[2]:
                st.markdown("**Universidades con facturación**")
                st.caption("Universidades donde se detectaron facturas o documentos similares.")
                if st.button("Ver universidades con facturas", key="qa_unis_invoices"):
                    _navigate_to("Organizaciones", org_only_unis_invoices=True)

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Universidades con actividad de cotización**")
                uni = _load_df(
                    conn,
                    """
                    SELECT
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      quote_email_count AS cotiz_email,
                      quote_doc_count AS cotiz_docs
                    FROM organization_master
                    WHERE organization_type_guess='education'
                      AND (quote_email_count > 0 OR quote_doc_count > 0)
                    ORDER BY (quote_email_count + quote_doc_count) DESC, total_emails DESC
                    LIMIT 12
                    """,
                )
                if uni.empty:
                    st.info("No se detectó actividad de cotización en organizaciones tipo educación.")
                else:
                    st.dataframe(uni, use_container_width=True, hide_index=True)

            with c2:
                st.markdown("**Organizaciones con actividad de factura**")
                inv = _load_df(
                    conn,
                    """
                    SELECT
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      invoice_email_count AS factura_email,
                      invoice_doc_count AS factura_docs
                    FROM organization_master
                    WHERE invoice_email_count > 0 OR invoice_doc_count > 0
                    ORDER BY (invoice_email_count + invoice_doc_count) DESC, total_emails DESC
                    LIMIT 12
                    """,
                )
                if inv.empty:
                    st.info("No se detectó actividad de factura en el mart actual.")
                else:
                    st.dataframe(inv, use_container_width=True, hide_index=True)

            with st.expander("Informe estático (HTML)"):
                st.markdown(
                    "La versión estática completa del informe se encuentra en el entorno de análisis en:\n\n"
                    "`reports/out/20260317_162013/index.html`\n\n"
                    "Esta app muestra una vista dinámica del mismo mart; "
                    "el informe HTML sigue siendo la referencia narrativa detallada."
                )

            # Radar de cotizaciones: organizaciones, contactos y cuentas dormidas.
            st.divider()
            st.markdown("### Radar de cotizaciones")
            st.caption(
                "Vista rápida de organizaciones y contactos con **alta actividad histórica de cotización**. "
                "Incluye correos donde se habla de cotizar y documentos detectados como cotización."
            )

            col_orgs, col_contacts = st.columns(2)

            with col_orgs:
                st.markdown("#### Organizaciones con mayor actividad de cotización")
                radar_orgs = _load_df(
                    conn,
                    """
                    SELECT
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      organization_type_guess AS tipo_org,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      quote_email_count AS cotiz_email,
                      quote_doc_count AS cotiz_docs,
                      business_doc_email_count AS doc_emails,
                      top_equipment_tags AS equipos
                    FROM organization_master
                    WHERE quote_email_count > 0 OR quote_doc_count > 0
                    ORDER BY (quote_email_count + quote_doc_count) DESC, total_emails DESC
                    LIMIT 15
                    """,
                )
                if radar_orgs.empty:
                    st.info("No se encontraron organizaciones con actividad clara de cotización.")
                else:
                    radar_orgs_display = radar_orgs.copy()
                    radar_orgs_display["tipo_org"] = radar_orgs_display["tipo_org"].apply(
                        lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                    )
                    radar_orgs_display = radar_orgs_display.rename(
                        columns={
                            "dominio": "Dominio",
                            "organizacion": "Organización",
                            "tipo_org": "Tipo de organización",
                            "primera": "Primera actividad",
                            "ultima": "Última actividad",
                            "total": "Total de correos",
                            "cotiz_email": "Correos con cotización",
                            "cotiz_docs": "Documentos de cotización",
                            "doc_emails": "Correos con documentos comerciales",
                            "equipos": "Equipos asociados (heurístico)",
                        }
                    )
                    st.dataframe(radar_orgs_display, use_container_width=True, hide_index=True)

            with col_contacts:
                st.markdown("#### Contactos con mayor actividad de cotización")
                radar_contacts = _load_df(
                    conn,
                    """
                    SELECT
                      email,
                      domain AS dominio,
                      organization_name_guess AS organizacion,
                      organization_type_guess AS tipo_org,
                      first_seen_at AS primera,
                      last_seen_at AS ultima,
                      total_emails AS total,
                      quote_email_count AS cotiz_email,
                      business_doc_email_count AS doc_emails,
                      top_equipment_tags AS equipos
                    FROM contact_master
                    WHERE quote_email_count > 0
                    ORDER BY quote_email_count DESC, total_emails DESC
                    LIMIT 15
                    """,
                )
                if radar_contacts.empty:
                    st.info("No se encontraron contactos con actividad clara de cotización.")
                else:
                    radar_contacts_display = radar_contacts.copy()
                    radar_contacts_display["tipo_org"] = radar_contacts_display["tipo_org"].apply(
                        lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                    )
                    radar_contacts_display = radar_contacts_display.rename(
                        columns={
                            "email": "Contacto (email)",
                            "dominio": "Dominio",
                            "organizacion": "Organización",
                            "tipo_org": "Tipo de organización",
                            "primera": "Primera actividad",
                            "ultima": "Última actividad",
                            "total": "Total de correos",
                            "cotiz_email": "Correos con cotización",
                            "doc_emails": "Correos con documentos comerciales",
                            "equipos": "Equipos asociados (heurístico)",
                        }
                    )
                    st.dataframe(radar_contacts_display, use_container_width=True, hide_index=True)

            # Cuentas dormidas con historial de cotización (basado en señales heurísticas).
            st.markdown("#### Cuentas dormidas con historial de cotización")
            dormant = _load_df(
                conn,
                """
                SELECT
                  s.entity_key AS email,
                  s.score,
                  s.created_at,
                  c.domain AS dominio,
                  c.organization_name_guess AS organizacion,
                  c.organization_type_guess AS tipo_org,
                  c.first_seen_at,
                  c.last_seen_at,
                  c.total_emails,
                  c.quote_email_count,
                  c.business_doc_email_count,
                  c.top_equipment_tags
                FROM opportunity_signals s
                JOIN contact_master c ON c.email = s.entity_key
                WHERE s.signal_type = 'dormant_contact'
                ORDER BY s.score DESC, s.created_at DESC
                LIMIT 30
                """,
            )
            if dormant.empty:
                st.info(
                    "Por ahora no se detectaron **cuentas dormidas** con historial de cotización significativo "
                    "según las señales heurísticas actuales."
                )
            else:
                dormant_display = dormant.copy()
                dormant_display["tipo_org"] = dormant_display["tipo_org"].apply(
                    lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                )
                dormant_display = dormant_display.rename(
                    columns={
                        "email": "Contacto (email)",
                        "dominio": "Dominio",
                        "organizacion": "Organización",
                        "tipo_org": "Tipo de organización",
                        "first_seen_at": "Primera actividad",
                        "last_seen_at": "Última actividad registrada",
                        "total_emails": "Total de correos",
                        "quote_email_count": "Correos con cotización",
                        "business_doc_email_count": "Correos con documentos comerciales",
                        "top_equipment_tags": "Equipos asociados (heurístico)",
                        "score": "Intensidad de la señal de cuenta dormida",
                        "created_at": "Mart (regenerado)",
                    }
                )
                st.dataframe(dormant_display, use_container_width=True, hide_index=True)
                st.caption(
                    "`Mart (regenerado)`: timestamp de la fila en la última reconstrucción de señales, no del último correo. "
                    "Estas cuentas combinan historial de cotización con ausencia de actividad reciente; candidatas a reactivación."
                )

            st.divider()
            st.markdown("### Explorador por equipo")
            st.caption("Ahora está en una sección dedicada para una navegación más clara.")
            if st.button("Ir a Equipos", key="go_to_equipos"):
                _navigate_to("Equipos")

            return

        if page == "Equipos":
            _render_equipment_page(conn)
            return

        if page == "Contactos":
            st.subheader("Contactos")
            q = st.text_input("Buscar (email / dominio / organización)", value="")
            min_total = st.number_input("Mínimo de correos", min_value=0, value=3, step=1)
            hide_suppressed = st.checkbox("Ocultar emails marcados como rebotados / no contactar", value=True)
            st.caption("Busca por email, dominio u organización. Se priorizan coincidencias más exactas.")

            dfc = _load_df(
                conn,
                """
                SELECT
                  email, domain AS dominio, organization_name_guess AS organizacion,
                  organization_type_guess AS tipo_org,
                  first_seen_at AS primera, last_seen_at AS ultima,
                  total_emails AS total,
                  quote_email_count AS cotiz_email,
                  invoice_email_count AS factura_email,
                  purchase_email_count AS compra_email,
                  business_doc_email_count AS doc_emails,
                  top_equipment_tags AS equipos
                FROM contact_master
                """,
            )
            dfc = dfc[dfc["total"] >= int(min_total)]
            qn = _normalize_query(q)
            if qn:
                score = _search_relevance_score(dfc, qn, ["email", "dominio", "organizacion"])
                dfc = dfc.assign(_search_score=score)
                dfc = dfc[dfc["_search_score"] > 0]
                dfc = dfc.sort_values(["_search_score", "total", "ultima"], ascending=[False, False, False])
            else:
                dfc = dfc.sort_values(["total", "ultima"], ascending=[False, False])
            supp_map = fetch_contact_email_suppression_map(conn, dfc["email"].dropna().astype(str).tolist())
            if supp_map:
                dfc["email_suppressed"] = dfc["email"].map(
                    lambda x: "Sí" if str(x).strip().lower() in supp_map else ""
                )
                if hide_suppressed:
                    dfc = dfc[dfc["email_suppressed"] != "Sí"]
            st.caption(f"Resultados: {len(dfc):,}")
            # Nombres de columnas más amigables para la tabla principal.
            dfc_display = dfc.rename(
                columns={
                    "email_suppressed": "Rebotado / bloqueado",
                    "dominio": "Dominio",
                    "organizacion": "Organización",
                    "tipo_org": "Tipo de organización",
                    "primera": "Primera interacción",
                    "ultima": "Última interacción",
                    "total": "Total de correos",
                    "cotiz_email": "Correos con cotización",
                    "factura_email": "Correos con factura",
                    "compra_email": "Correos de compra/pedido",
                    "doc_emails": "Correos con documentos comerciales",
                    "equipos": "Equipos mencionados",
                }
            )
            st.dataframe(dfc_display.head(800), use_container_width=True, hide_index=True)

            st.divider()
            sel = st.selectbox("Seleccionar contacto", options=[""] + dfc["email"].head(400).tolist())
            if sel:
                row = _load_df(conn, "SELECT * FROM contact_master WHERE email=?", (sel,))
                if not row.empty:
                    r = row.iloc[0]
                    supp = fetch_contact_email_suppression_row(conn, str(r["email"]))
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("**Identidad del contacto**")
                        _render_copyable_email_row(str(r["email"]), key=f"copy_contact_{r['email']}")
                        if supp:
                            st.warning(
                                "Email marcado para no reutilizarse: "
                                f"{contact_suppression_reason_label(str(supp.get('suppression_reason_code') or ''))}."
                            )
                        st.markdown(f"- Dominio: `{r['domain']}`" if r.get("domain") else "- Dominio: (no detectado)")
                        org_name = r.get("organization_name_guess") or "Sin nombre de organización"
                        st.markdown(f"- Organización: {org_name}")
                        st.markdown(f"- Tipo de organización: {_friendly_org_type(r.get('organization_type_guess'))}")

                    with col2:
                        st.markdown("**Actividad en el tiempo**")
                        st.markdown(f"- Primera interacción: {r.get('first_seen_at') or 'N/D'}")
                        st.markdown(f"- Última interacción: {r.get('last_seen_at') or 'N/D'}")
                        total = r.get("total_emails") or 0
                        st.markdown(f"- Total de correos: {int(total):,}")
                        quotes = r.get("quote_email_count") or 0
                        invoices = r.get("invoice_email_count") or 0
                        purchases = r.get("purchase_email_count") or 0
                        st.markdown(
                            f"Se han detectado **{int(quotes)}** correos con términos de cotización, "
                            f"**{int(invoices)}** con términos de factura y "
                            f"**{int(purchases)}** relacionados con compra/pedido."
                        )

                    with col3:
                        st.markdown("**Documentos y equipos**")
                        doc_emails = r.get("business_doc_email_count") or r.get("business_doc_email_count".upper(), 0)
                        st.markdown(
                            f"- Correos con documentos comerciales: {int(doc_emails) if pd.notna(doc_emails) else 0}"
                        )
                        equipos = r.get("top_equipment_tags")
                        if equipos:
                            st.markdown("- Equipos más mencionados:")
                            st.markdown(equipos)
                        else:
                            st.markdown("- Equipos más mencionados: (no detectados)")

                    with st.expander("Ver datos técnicos del contacto"):
                        st.json(r.to_dict())

                    if not contact_email_suppression_table_exists(conn):
                        if _ensure_contact_email_suppression_ddl(db_path):
                            st.info("Se creó la tabla para registrar rebotes/bloqueos de emails. Recargue la vista si no la ve aún.")
                        else:
                            st.caption("Si quiere registrar rebotes desde la app, use una base grabable para crear la tabla de supresión.")

                    rw_supp = streamlit_contact_suppression_rw_enabled()
                    st.markdown("### Estado del email")
                    if supp:
                        st.write(
                            {
                                "Estado": contact_suppression_reason_label(str(supp.get("suppression_reason_code") or "")),
                                "Detalle": supp.get("suppression_reason_text") or "—",
                                "Origen": supp.get("suppression_source") or "—",
                                "Último rebote": supp.get("last_bounced_at") or "—",
                                "Actualizado": supp.get("updated_at") or "—",
                                "Por": supp.get("updated_by") or "—",
                            }
                        )
                    else:
                        st.caption("Este email no está marcado como rebotado o bloqueado.")

                    if rw_supp:
                        with st.form(f"contact_suppression_form_{r['email']}", clear_on_submit=False):
                            st.markdown("#### Marcar / actualizar rebote o bloqueo")
                            reason_idx = 0
                            if supp and str(supp.get("suppression_reason_code") or "") in SUPPRESSION_REASON_CODES:
                                reason_idx = list(SUPPRESSION_REASON_CODES).index(str(supp.get("suppression_reason_code")))
                            st_reason = st.selectbox(
                                "Motivo",
                                options=list(SUPPRESSION_REASON_CODES),
                                index=reason_idx,
                                format_func=contact_suppression_reason_label,
                                key=f"contact_supp_reason_{r['email']}",
                            )
                            st_reason_text = st.text_area(
                                "Detalle breve (opcional)",
                                value=str(supp.get("suppression_reason_text") or "") if supp else "",
                                height=90,
                                key=f"contact_supp_reason_text_{r['email']}",
                            )
                            st_source = st.text_input(
                                "Origen del dato",
                                value=str(supp.get("suppression_source") or "rebote manual") if supp else "rebote manual",
                                key=f"contact_supp_source_{r['email']}",
                            )
                            st_bounced_at = st.text_input(
                                "Fecha/hora del rebote (opcional)",
                                value=str(supp.get("last_bounced_at") or "") if supp else "",
                                key=f"contact_supp_bounced_at_{r['email']}",
                            )
                            st_by = st.text_input(
                                "Quién actualiza (opcional)",
                                value=str(supp.get("updated_by") or "") if supp else "",
                                key=f"contact_supp_by_{r['email']}",
                            )
                            submitted = st.form_submit_button("Guardar marca de rebote/bloqueo")
                            if submitted:
                                conn_rw = sqlite3.connect(str(db_path), timeout=60.0)
                                try:
                                    ensure_contact_email_suppression_table(conn_rw)
                                    payload = validate_contact_email_suppression_payload(
                                        email=str(r["email"]),
                                        suppression_reason_code=st_reason,
                                        suppression_reason_text=st_reason_text or None,
                                        suppression_source=st_source or None,
                                        last_bounced_at=st_bounced_at or None,
                                        updated_by=st_by or None,
                                    )
                                    upsert_contact_email_suppression(conn_rw, payload=payload)
                                    conn_rw.commit()
                                    st.success("Email marcado para no reutilizarse.")
                                    st.rerun()
                                except ValueError as err:
                                    st.error(str(err))
                                finally:
                                    conn_rw.close()
                        if supp and st.button("Quitar marca de rebote/bloqueo", key=f"contact_supp_delete_{r['email']}"):
                            conn_rw = sqlite3.connect(str(db_path), timeout=60.0)
                            try:
                                ensure_contact_email_suppression_table(conn_rw)
                                delete_contact_email_suppression(conn_rw, str(r["email"]))
                                conn_rw.commit()
                                st.success("Marca de rebote eliminada.")
                                st.rerun()
                            finally:
                                conn_rw.close()
                    else:
                        st.info(
                            "Para registrar rebotes desde esta app, use una base grabable y habilite `ORIGENLAB_STREAMLIT_CONTACT_SUPPRESSION_RW=1`."
                        )

                    # Drill-down: documentos asociados al dominio del contacto.
                    st.markdown("### Documentos asociados a este contacto")
                    dom = r.get("domain")
                    if dom:
                        docs = _load_df(
                            conn,
                            """
                            SELECT
                              attachment_id,
                              sent_at,
                              doc_type,
                              filename,
                              sender_domain,
                              equipment_tags
                            FROM document_master
                            WHERE sender_domain = ?
                            ORDER BY sent_at DESC, attachment_id DESC
                            LIMIT 10
                            """,
                            (dom,),
                        )
                        if docs.empty:
                            st.info("No se encontraron documentos comerciales asociados a este contacto.")
                        else:
                            docs_display = docs.copy()
                            docs_display["doc_type"] = docs_display["doc_type"].apply(
                                lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
                            )
                            docs_display = docs_display.rename(
                                columns={
                                    "sent_at": "Fecha envío",
                                    "doc_type": "Tipo de documento",
                                    "filename": "Archivo",
                                    "sender_domain": "Dominio remitente",
                                    "equipment_tags": "Equipos mencionados",
                                }
                            )
                            st.dataframe(docs_display, use_container_width=True, hide_index=True)
                    else:
                        st.info("Este contacto no tiene dominio asociado para buscar documentos relacionados.")

                    # Drill-down: señales asociadas al contacto.
                    st.markdown("### Señales heurísticas asociadas a este contacto")
                    sig = _load_df(
                        conn,
                        """
                        SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
                        FROM opportunity_signals
                        WHERE entity_kind = 'contact' AND entity_key = ?
                        ORDER BY score DESC, created_at DESC
                        """,
                        (r["email"],),
                    )
                    if sig.empty:
                        st.info("No se detectaron señales específicas para este contacto.")
                    else:
                        sig["señal"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[0])
                        sig["explicación"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[1])
                        sig_display = sig[["señal", "explicación", "score", "created_at"]]
                        sig_display = sig_display.rename(
                            columns={
                                "score": "Intensidad de la señal",
                                "created_at": "Mart (regenerado)",
                            }
                        )
                        st.caption(
                            "**Mart (regenerado)**: regeneración de `opportunity_signals`, no fecha del correo."
                        )
                        st.dataframe(sig_display, use_container_width=True, hide_index=True)
                        with st.expander("Ver detalles técnicos de las señales"):
                            st.dataframe(
                                sig[["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]],
                                use_container_width=True,
                                hide_index=True,
                            )
            return

        if page == "Organizaciones":
            st.subheader("Organizaciones")
            q = st.text_input("Buscar (dominio / nombre)", value="", key="org_q_basic")
            min_total = st.number_input("Mínimo correos", min_value=0, value=8, step=1, key="org_min_basic")
            min_contacts = st.number_input(
                "Mínimo contactos", min_value=0, value=2, step=1, key="org_min_c_basic"
            )
            st.caption("Busca por dominio o nombre. Se priorizan coincidencias más exactas.")
            solo_unis_default = _consume_nav_flag("org_only_unis", False)
            solo_unis = st.checkbox(
                "Solo universidades con actividad de cotización",
                value=solo_unis_default,
            )

            dfo = _load_df(
                conn,
                """
                SELECT
                  domain AS dominio,
                  organization_name_guess AS organizacion,
                  organization_type_guess AS tipo_org,
                  first_seen_at AS primera,
                  last_seen_at AS ultima,
                  total_emails AS total,
                  total_contacts AS contactos,
                  quote_email_count AS cotiz_email,
                  invoice_email_count AS factura_email,
                  purchase_email_count AS compra_email,
                  business_doc_email_count AS doc_emails,
                  top_equipment_tags AS equipos,
                  key_contacts AS contactos_clave
                FROM organization_master
                """,
            )
            dfo = dfo[dfo["total"] >= int(min_total)]
            dfo = dfo[dfo["contactos"] >= int(min_contacts)]
            if solo_unis:
                dfo = dfo[
                    (dfo["tipo_org"] == "education")
                    & ((dfo["cotiz_email"] > 0) | (dfo["doc_emails"] > 0))
                ]
            # Filtro adicional desde quick-actions: solo organizaciones con facturas.
            if _consume_nav_flag("org_only_invoices", False):
                dfo = dfo[(dfo["factura_email"] > 0)]
            # Filtro adicional: universidades con facturación.
            if _consume_nav_flag("org_only_unis_invoices", False):
                dfo = dfo[
                    (dfo["tipo_org"] == "education")
                    & (dfo["factura_email"] > 0)
                ]

            qn = _normalize_query(q)
            if qn:
                score = _search_relevance_score(dfo, qn, ["dominio", "organizacion"])
                dfo = dfo.assign(_search_score=score)
                dfo = dfo[dfo["_search_score"] > 0]
                dfo = dfo.sort_values(["_search_score", "total", "ultima"], ascending=[False, False, False])
            else:
                dfo = dfo.sort_values(["total", "ultima"], ascending=[False, False])
            st.caption(f"Resultados: {len(dfo):,}")

            # Nombres de columnas más amigables para la tabla principal.
            dfo_display = dfo.rename(
                columns={
                    "dominio": "Dominio",
                    "organizacion": "Organización",
                    "tipo_org": "Tipo de organización",
                    "primera": "Primera interacción",
                    "ultima": "Última interacción",
                    "total": "Total de correos",
                    "contactos": "Total de contactos",
                    "cotiz_email": "Correos con cotización",
                    "factura_email": "Correos con factura",
                    "compra_email": "Correos de compra/pedido",
                    "doc_emails": "Correos con documentos comerciales",
                    "equipos": "Equipos mencionados",
                    "contactos_clave": "Contactos clave (texto heurístico)",
                }
            )
            st.dataframe(dfo_display.head(800), use_container_width=True, hide_index=True)

            # Vista resumida de proveedores detectados (heurística basada en facturas y documentos comerciales).
            st.divider()
            st.markdown("### Proveedores detectados")
            st.caption(
                "Organizaciones tratadas como **proveedores** en base a facturas, órdenes de compra, "
                "documentos comerciales y listas de precios detectadas en el archivo histórico."
            )

            proveedores = _load_df(
                conn,
                """
                SELECT
                  domain AS dominio,
                  organization_name_guess AS organizacion,
                  organization_type_guess AS tipo_org,
                  first_seen_at AS primera,
                  last_seen_at AS ultima,
                  total_emails AS total,
                  total_contacts AS contactos,
                  quote_email_count AS cotiz_email,
                  invoice_email_count AS factura_email,
                  invoice_doc_count AS factura_docs,
                  purchase_email_count AS compra_email,
                  business_doc_email_count AS doc_emails,
                  top_equipment_tags AS equipos,
                  key_contacts AS contactos_clave
                FROM organization_master
                """,
            )
            proveedor_docs = _load_df(
                conn,
                """
                SELECT sender_domain, doc_type
                FROM document_master
                WHERE doc_type IN ('price_list', 'datasheet', 'purchase_order')
                """,
            )
            dominios_lista = set(
                proveedor_docs[proveedor_docs["doc_type"] == "price_list"]["sender_domain"].dropna().tolist()
            )
            dominios_ficha = set(
                proveedor_docs[proveedor_docs["doc_type"] == "datasheet"]["sender_domain"].dropna().tolist()
            )
            dominios_compra = set(
                proveedor_docs[proveedor_docs["doc_type"] == "purchase_order"]["sender_domain"].dropna().tolist()
            )

            if not proveedores.empty:
                proveedores["es_proveedor"] = (
                    (proveedores["factura_email"] > 0)
                    | (proveedores["factura_docs"] > 0)
                    | (proveedores["compra_email"] > 0)
                    | (proveedores["doc_emails"] > 0)
                    | proveedores["dominio"].isin(dominios_lista)
                    | proveedores["dominio"].isin(dominios_ficha)
                    | proveedores["dominio"].isin(dominios_compra)
                )
                proveedores = proveedores[proveedores["es_proveedor"]]

            if proveedores.empty:
                st.info(
                    "Aún no se detectan organizaciones con suficiente evidencia documental para clasificarlas como "
                    "proveedores. Cuando el mart tenga facturas u órdenes de compra, aparecerán aquí."
                )
            else:
                proveedores["tiene_lista_precios"] = proveedores["dominio"].isin(dominios_lista)
                proveedores["tiene_ficha_tecnica"] = proveedores["dominio"].isin(dominios_ficha)
                proveedores["tiene_documentos_compra"] = proveedores["dominio"].isin(dominios_compra)

                def _evidencia_proveedor(row: pd.Series) -> str:
                    partes: list[str] = []
                    if (row.get("factura_email") or 0) > 0 or (row.get("factura_docs") or 0) > 0:
                        partes.append("facturas detectadas")
                    if (row.get("compra_email") or 0) > 0 or row.get("tiene_documentos_compra"):
                        partes.append("órdenes de compra / correos de compra")
                    if (row.get("doc_emails") or 0) > 0:
                        partes.append("correos con documentos comerciales")
                    if row.get("tiene_lista_precios"):
                        partes.append("listas de precios")
                    if row.get("tiene_ficha_tecnica"):
                        partes.append("fichas técnicas")
                    return ", ".join(partes) if partes else "Evidencia comercial limitada"

                proveedores["evidencia"] = proveedores.apply(_evidencia_proveedor, axis=1)
                proveedores["tipo_org"] = proveedores["tipo_org"].apply(
                    lambda x: _friendly_org_type(str(x)) if pd.notna(x) else _friendly_org_type(None)
                )

                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    f_facturas = st.checkbox("Solo con facturas", value=False)
                with fc2:
                    f_listas = st.checkbox("Solo con listas de precios / fichas técnicas", value=False)
                with fc3:
                    f_compra = st.checkbox("Solo con órdenes de compra / compra", value=False)

                proveedores_filtrado = proveedores.copy()
                if f_facturas:
                    proveedores_filtrado = proveedores_filtrado[
                        (proveedores_filtrado["factura_email"] > 0) | (proveedores_filtrado["factura_docs"] > 0)
                    ]
                if f_listas:
                    proveedores_filtrado = proveedores_filtrado[
                        proveedores_filtrado["tiene_lista_precios"] | proveedores_filtrado["tiene_ficha_tecnica"]
                    ]
                if f_compra:
                    proveedores_filtrado = proveedores_filtrado[
                        (proveedores_filtrado["compra_email"] > 0) | proveedores_filtrado["tiene_documentos_compra"]
                    ]

                proveedores_filtrado = proveedores_filtrado.sort_values(
                    ["factura_docs", "factura_email", "doc_emails", "total"],
                    ascending=[False, False, False, False],
                )

                proveedores_display = proveedores_filtrado.rename(
                    columns={
                        "dominio": "Dominio",
                        "organizacion": "Organización",
                        "tipo_org": "Tipo de organización",
                        "primera": "Primera actividad",
                        "ultima": "Última actividad",
                        "total": "Total de correos",
                        "contactos": "Total de contactos",
                        "cotiz_email": "Correos con cotización",
                        "factura_email": "Correos con factura",
                        "factura_docs": "Documentos tipo factura",
                        "compra_email": "Correos de compra/pedido",
                        "doc_emails": "Correos con documentos comerciales",
                        "equipos": "Equipos asociados (heurístico)",
                        "contactos_clave": "Contactos clave (texto heurístico)",
                        "evidencia": "Evidencia de proveedor",
                    }
                )
                st.dataframe(proveedores_display.head(200), use_container_width=True, hide_index=True)

            st.divider()
            sel = st.selectbox("Seleccionar dominio", options=[""] + dfo["dominio"].head(400).tolist())
            if sel:
                row = _load_df(conn, "SELECT * FROM organization_master WHERE domain=?", (sel,))
                if not row.empty:
                    r = row.iloc[0]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("**Identidad de la organización**")
                        st.markdown(f"- Dominio: `{r['domain']}`")
                        org_name = r.get("organization_name_guess") or "Sin nombre de organización"
                        st.markdown(f"- Organización: {org_name}")
                        st.markdown(f"- Tipo de organización: {_friendly_org_type(r.get('organization_type_guess'))}")

                    with col2:
                        st.markdown("**Actividad en el tiempo**")
                        st.markdown(f"- Primera interacción: {r.get('first_seen_at') or 'N/D'}")
                        st.markdown(f"- Última interacción: {r.get('last_seen_at') or 'N/D'}")
                        total = r.get("total_emails") or 0
                        contactos = r.get("total_contacts") or 0
                        st.markdown(f"- Total de correos: {int(total):,}")
                        st.markdown(f"- Total de contactos detectados: {int(contactos):,}")

                        quotes = r.get("quote_email_count") or 0
                        invoices = r.get("invoice_email_count") or 0
                        purchases = r.get("purchase_email_count") or 0
                        st.markdown(
                            f"Correos detectados: **{int(quotes)}** con cotización, "
                            f"**{int(invoices)}** con factura y "
                            f"**{int(purchases)}** de compra/pedido."
                        )

                    with col3:
                        st.markdown("**Documentos y equipos**")
                        doc_emails = r.get("business_doc_email_count") or 0
                        st.markdown(f"- Correos con documentos comerciales: {int(doc_emails)}")
                        equipos = r.get("top_equipment_tags")
                        if equipos:
                            st.markdown("- Equipos más mencionados:")
                            st.markdown(equipos)
                        else:
                            st.markdown("- Equipos más mencionados: (no detectados)")
                        key_contacts = r.get("key_contacts")
                        if key_contacts:
                            st.markdown("**Contactos clave (texto heurístico)**")
                            st.markdown(key_contacts)

                    with st.expander("Ver datos técnicos de la organización"):
                        st.json(r.to_dict())

                    # Drill-down: contactos clave de esta organización.
                    st.markdown("### Contactos de esta organización")
                    contacts = _load_df(
                        conn,
                        """
                        SELECT
                          email,
                          domain AS dominio,
                          organization_name_guess AS organizacion,
                          first_seen_at AS primera,
                          last_seen_at AS ultima,
                          total_emails AS total,
                          quote_email_count AS cotiz_email,
                          invoice_email_count AS factura_email,
                          purchase_email_count AS compra_email,
                          business_doc_email_count AS doc_emails
                        FROM contact_master
                        WHERE domain = ?
                        ORDER BY total_emails DESC, last_seen_at DESC
                        LIMIT 10
                        """,
                        (r["domain"],),
                    )
                    if contacts.empty:
                        st.info("No se encontraron contactos asociados a esta organización.")
                    else:
                        contacts_supp_map = fetch_contact_email_suppression_map(
                            conn, contacts["email"].dropna().astype(str).tolist()
                        )
                        if contacts_supp_map:
                            contacts["email_suppressed"] = contacts["email"].map(
                                lambda x: "Sí" if str(x).strip().lower() in contacts_supp_map else ""
                            )
                        contacts_display = contacts.rename(
                            columns={
                                "email_suppressed": "Rebotado / bloqueado",
                                "dominio": "Dominio",
                                "organizacion": "Organización",
                                "primera": "Primera interacción",
                                "ultima": "Última interacción",
                                "total": "Total de correos",
                                "cotiz_email": "Correos con cotización",
                                "factura_email": "Correos con factura",
                                "compra_email": "Correos de compra/pedido",
                                "doc_emails": "Correos con documentos comerciales",
                            }
                        )
                        st.dataframe(contacts_display, use_container_width=True, hide_index=True)
                        st.caption("Copiar email de un contacto:")
                        for i, email in enumerate(contacts["email"].dropna().astype(str).tolist()):
                            _render_copyable_email_row(email, key=f"copy_org_contact_{r['domain']}_{i}", prefix="Contacto")

                    # Drill-down: documentos recientes de la organización.
                    st.markdown("### Documentos comerciales recientes")
                    docs = _load_df(
                        conn,
                        """
                        SELECT
                          attachment_id,
                          sent_at,
                          doc_type,
                          filename,
                          sender_domain,
                          equipment_tags
                        FROM document_master
                        WHERE sender_domain = ?
                        ORDER BY sent_at DESC, attachment_id DESC
                        LIMIT 10
                        """,
                        (r["domain"],),
                    )
                    if docs.empty:
                        st.info("No se encontraron documentos comerciales recientes para esta organización.")
                    else:
                        docs_display = docs.copy()
                        docs_display["doc_type"] = docs_display["doc_type"].apply(
                            lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
                        )
                        docs_display = docs_display.rename(
                            columns={
                                "sent_at": "Fecha envío",
                                "doc_type": "Tipo de documento",
                                "filename": "Archivo",
                                "sender_domain": "Dominio remitente",
                                "equipment_tags": "Equipos mencionados",
                            }
                        )
                        st.dataframe(docs_display, use_container_width=True, hide_index=True)

                    # Drill-down: señales relacionadas con la organización.
                    st.markdown("### Señales heurísticas relacionadas con esta organización")
                    sig = _load_df(
                        conn,
                        """
                        SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
                        FROM opportunity_signals
                        WHERE entity_kind = 'organization' AND entity_key = ?
                        ORDER BY score DESC, created_at DESC
                        """,
                        (r["domain"],),
                    )
                    if sig.empty:
                        st.info("No se detectaron señales específicas para esta organización.")
                    else:
                        sig["señal"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[0])
                        sig["explicación"] = sig["signal_type"].apply(lambda x: _signal_label(str(x))[1])
                        sig_display = sig[["señal", "explicación", "score", "created_at"]]
                        sig_display = sig_display.rename(
                            columns={
                                "score": "Intensidad de la señal",
                                "created_at": "Mart (regenerado)",
                            }
                        )
                        st.caption(
                            "**Mart (regenerado)**: regeneración de `opportunity_signals`, no fecha del correo."
                        )
                        st.dataframe(sig_display, use_container_width=True, hide_index=True)
                        with st.expander("Ver detalles técnicos de las señales"):
                            st.dataframe(
                                sig[["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]],
                                use_container_width=True,
                                hide_index=True,
                            )
            return

        if page == "Documentos":
            st.subheader("Documentos")
            q = st.text_input("Buscar (archivo o contenido)", value="", key="doc_q_basic")
            dfd = _load_df(
                conn,
                """
                SELECT
                  attachment_id, sent_at, doc_type, filename, sender_domain,
                  extracted_preview_clean, preview_quality_score, equipment_tags
                FROM document_master
                """,
            )
            # Quick-action: solo documentos de cotización.
            if st.session_state.get("docs_only_quotes"):
                dfd = dfd[dfd["doc_type"] == "quote"]

            if q.strip():
                ql = q.strip().lower()
                mask = (
                    dfd["filename"].fillna("").str.lower().str.contains(ql)
                    | dfd["extracted_preview_clean"].fillna("").str.lower().str.contains(ql)
                )
                dfd = dfd[mask]
            dfd = dfd.sort_values(["sent_at", "attachment_id"], ascending=[False, False])
            dfd_display = dfd.copy()
            dfd_display["doc_type"] = dfd_display["doc_type"].apply(
                lambda x: _friendly_doc_type(str(x)) if pd.notna(x) else _friendly_doc_type(None)
            )
            dfd_display = dfd_display.rename(
                columns={
                    "sent_at": "Fecha envío",
                    "doc_type": "Tipo de documento",
                    "filename": "Archivo",
                    "sender_domain": "Dominio remitente",
                    "extracted_preview_clean": "Texto relevante encontrado",
                    "preview_quality_score": "Calidad de la extracción",
                    "equipment_tags": "Equipos mencionados",
                }
            )
            st.dataframe(dfd_display.head(400), use_container_width=True, hide_index=True)

            # Detalle resumido de un documento seleccionado.
            st.divider()
            if not dfd.empty:
                options = dfd.head(200).apply(
                    lambda r: f"{r['attachment_id']} — {str(r['sent_at'])[:10]} — {r['filename']}",
                    axis=1,
                ).tolist()
                selected_label = st.selectbox(
                    "Ver detalle de un documento",
                    options=[""] + options,
                )
                if selected_label:
                    sel_id = int(selected_label.split(" — ")[0])
                    drow_df = _load_df(
                        conn,
                        """
                        SELECT
                          attachment_id,
                          sent_at,
                          doc_type,
                          filename,
                          sender_domain,
                          extracted_preview_clean,
                          preview_quality_score,
                          equipment_tags
                        FROM document_master
                        WHERE attachment_id = ?
                        """,
                        (sel_id,),
                    )
                    if not drow_df.empty:
                        d = drow_df.iloc[0]
                        st.markdown("### Resumen del documento seleccionado")
                        st.markdown(
                            f"Detectado como **{_friendly_doc_type(d.get('doc_type'))}** "
                            "según el contenido del adjunto."
                        )
                        st.markdown(f"- Fecha de envío: {d.get('sent_at')}")
                        st.markdown(f"- Archivo: `{d.get('filename')}`")
                        st.markdown(f"- Dominio remitente: `{d.get('sender_domain')}`")
                        score = d.get("preview_quality_score")
                        if pd.notna(score):
                            st.markdown(f"- Calidad de la extracción de texto: {score:.2f}")
                        equipos = d.get("equipment_tags")
                        if equipos:
                            st.markdown(f"- Equipos mencionados: {equipos}")
                        else:
                            st.markdown("- Equipos mencionados: (no detectados)")

                        with st.expander("Ver texto extraído (resumen)"):
                            preview = d.get("extracted_preview_clean") or "(sin texto extraído disponible)"
                            st.write(preview)

                        with st.expander("Ver datos técnicos del documento"):
                            st.json(d.to_dict())
            return

        if page == "Candidatos comerciales":
            st.subheader("Candidatos comerciales (inteligencia comercial v1)")
            render_page_status(
                "Candidatos comerciales",
                note="Puede revisar la cola siempre; las acciones de aprobar, rechazar o posponer solo escriben en la base si el modo RW está habilitado.",
            )
            st.caption(
                "Cola de revisión humana sobre lo detectado en el correo. Los estados se guardan en la base "
                "(no reemplaza un CRM)."
            )
            with st.expander("Nota rápida", expanded=False):
                st.caption(
                    "Detalle técnico: vista `v_commercial_candidate_queue`. Las acciones de escritura generan "
                    "override y registro de auditoría; ver `docs/pipeline/COMMERCIAL_INTEL_V1.md`."
                )
            if not _has_table(conn, "v_commercial_candidate_queue"):
                st.warning(
                    "En este archivo SQLite no existe la vista **`v_commercial_candidate_queue`** "
                    "(capa Commercial Intelligence v1 no aplicada o base distinta a la del build)."
                )
                st.markdown(
                    "Desde **`apps/email-pipeline`** (mismo `ORIGENLAB_SQLITE_PATH` que muestra *Salud de datos*):\n\n"
                    "```bash\n"
                    "uv run python scripts/commercial/build_commercial_intel_v1.py\n"
                    "```\n\n"
                    "Primera vez o señales vacías: puede usar `--rebuild`. "
                    "Si la app corre en Docker, el volumen debe apuntar al **mismo** `emails.sqlite` "
                    "que actualiza el build."
                )
                st.caption(
                    "Documentación: `docs/pipeline/COMMERCIAL_INTEL_V1.md` · "
                    "Ejecución: `docs/RUNBOOK.md` (Commercial intelligence v1)."
                )
                return

            if SESSION_CI_TODAY_HINT in st.session_state:
                st.info(
                    "Sugerencia **Qué hacer hoy**: candidato `"
                    + st.session_state.pop(SESSION_CI_TODAY_HINT)
                    + "`. Revise la tabla inferior; los filtros pueden quedar en **pendiente de revisión**."
                )

            from origenlab_email_pipeline.commercial.commercial_intel_review import (
                QueueFilters,
                apply_review_action,
                fetch_queue_rows,
            )

            f1, f2, f3 = st.columns(3)
            with f1:
                fk = st.selectbox(
                    "Tipo de entidad",
                    ["(todas)", "organization", "contact", "opportunity"],
                    format_func=_fmt_ci_entity_kind,
                    key="ci_entity_kind",
                )
            with f2:
                stat_opts = [
                    "(todos)",
                    "new",
                    "needs_review",
                    "approved",
                    "rejected",
                    "snoozed",
                    "suppressed",
                ]
                st_sel = st.selectbox(
                    "Estado del candidato",
                    stat_opts,
                    format_func=_fmt_ci_status,
                    key="ci_status",
                )
            with f3:
                lim = st.number_input("Máx. filas", min_value=10, max_value=2000, value=300, step=10)

            f4, f5, f6 = st.columns(3)
            with f4:
                ctype = st.text_input(
                    "Tipo de candidato (solo organizaciones; texto en inglés si aplica)",
                    value="",
                    key="ci_ctype",
                )
            with f5:
                min_c = st.number_input("Confianza mín.", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
            with f6:
                min_s = st.number_input(
                    "Intensidad mín. (strength)",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.0,
                    step=0.05,
                )

            filters = QueueFilters(
                entity_kind=None if fk == "(todas)" else fk,
                review_status=None if st_sel == "(todos)" else st_sel,
                candidate_type=ctype.strip() or None,
                min_confidence=min_c if min_c > 0 else None,
                min_strength=min_s if min_s > 0 else None,
            )
            rows = fetch_queue_rows(conn, filters=filters, limit=int(lim))
            if not rows:
                st.info("Sin filas con los filtros actuales.")
            else:
                df = pd.DataFrame(rows)
                show = df.rename(
                    columns={
                        "entity_kind": "entidad",
                        "entity_key": "clave",
                        "status": "estado",
                        "confidence_score": "confianza",
                        "strength_score": "intensidad",
                        "reason_summary": "resumen",
                    }
                )
                st.dataframe(show, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("#### Acción sobre un candidato")
            rw_ok = os.environ.get("ORIGENLAB_STREAMLIT_COMMERCIAL_REVIEW_RW") == "1"
            if not rw_ok:
                st.info(
                    "**Solo lectura:** esta app suele abrir el SQLite en modo no modificable. "
                    "Para registrar aprobación, rechazo o posponer desde aquí, use una base grabable y la variable "
                    "`ORIGENLAB_STREAMLIT_COMMERCIAL_REVIEW_RW=1`. También puede usar el script: "
                    "`uv run python scripts/commercial/review_commercial_candidate.py`."
                )
            elif not rows:
                st.caption("Ajuste los filtros arriba para cargar candidatos y poder elegir uno.")
            else:
                pick_labels = [f"{r['entity_kind']} | {r['entity_key']}" for r in rows[:500]]
                choice = st.selectbox("Candidato", [""] + pick_labels, key="ci_pick")
                act = st.selectbox(
                    "Acción",
                    ["approve", "reject", "snooze"],
                    format_func=_fmt_ci_action,
                    key="ci_action",
                )
                note = st.text_input("Nota (opcional)", value="", key="ci_note")
                if st.button("Aplicar acción", key="ci_apply") and choice:
                    kind, _, ekey = choice.partition(" | ")
                    conn_rw = sqlite3.connect(str(db_path), timeout=60.0)
                    try:
                        apply_review_action(
                            conn_rw,
                            entity_kind=kind,
                            entity_key=ekey,
                            action=act,
                            actor="streamlit",
                            note=note,
                        )
                        st.success("Guardado (override + fila + auditoría si hubo cambio de estado).")
                        st.rerun()
                    except ValueError as err:
                        st.error(str(err))
                    finally:
                        conn_rw.close()
            return

        if page == "Oportunidades":
            st.subheader("Oportunidades")
            render_page_status("Oportunidades")
            dfs = _load_df(
                conn,
                """
                SELECT signal_type, entity_kind, entity_key, score, details_json, created_at
                FROM opportunity_signals
                ORDER BY score DESC, created_at DESC
                """,
            )
            dfs["señal"] = dfs["signal_type"].apply(lambda x: _signal_label(str(x))[0])
            dfs["explicación"] = dfs["signal_type"].apply(lambda x: _signal_label(str(x))[1])

            # Filtros amigables por tipo de señal, entidad y score mínimo.
            signal_options = ["Todas", "Cotización + documento", "Universidad con cotización", "Cuenta dormida", "Tema de equipo recurrente"]
            # Si venimos desde quick-action de cuentas dormidas, seleccionar por defecto esa opción.
            default_signal = 0
            if st.session_state.pop(SESSION_OPP_SIGNAL_FILTER, None) == "dormant_contact":
                default_signal = signal_options.index("Cuenta dormida")
            tipo_señal = st.selectbox("Tipo de señal", options=signal_options, index=default_signal)
            signal_map = {
                "Cotización + documento": "quote_email_plus_quote_doc",
                "Universidad con cotización": "education_with_quote_activity",
                "Cuenta dormida": "dormant_contact",
                "Tema de equipo recurrente": "repeated_equipment_theme",
            }
            if tipo_señal != "Todas":
                dfs = dfs[dfs["signal_type"] == signal_map[tipo_señal]]

            entity_options = ["Todas", "Contacto", "Organización"]
            tipo_entidad = st.selectbox("Entidad asociada", options=entity_options)
            if tipo_entidad == "Contacto":
                dfs = dfs[dfs["entity_kind"] == "contact"]
            elif tipo_entidad == "Organización":
                dfs = dfs[dfs["entity_kind"] == "organization"]

            min_score = st.number_input("Score mínimo de la señal", min_value=0.0, max_value=1000.0, value=0.0, step=1.0)
            dfs = dfs[dfs["score"] >= float(min_score)]

            # Panel rápido: señales por tipo + intensidad máxima para priorización.
            if not dfs.empty:
                summary = (
                    dfs.groupby("signal_type", dropna=False)
                    .agg(total=("signal_type", "count"), score_max=("score", "max"))
                    .reset_index()
                )
                summary["señal"] = summary["signal_type"].apply(lambda x: _signal_label(str(x))[0])
                summary = summary.sort_values(["total", "score_max"], ascending=[False, False]).head(6)
                st.markdown("#### Prioridad rápida")
                st.dataframe(
                    summary[["señal", "total", "score_max"]].rename(
                        columns={"total": "Cantidad", "score_max": "Score máximo"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            # Traducir entity_kind a etiquetas legibles.
            dfs_display = dfs.copy()
            dfs_display["Entidad"] = dfs_display["entity_kind"].map(
                {"contact": "Contacto", "organization": "Organización"}
            ).fillna(dfs_display["entity_kind"])

            main_cols = ["señal", "explicación", "Entidad", "entity_key", "score", "created_at"]
            dfs_display = dfs_display[main_cols].rename(
                columns={
                    "entity_key": "Clave (email/dominio)",
                    "score": "Intensidad de la señal",
                    "created_at": "Mart (regenerado)",
                }
            )

            st.caption(
                f"Resultados: {len(dfs_display):,}. **Mart (regenerado)** = instante de última ejecución de "
                "`build_business_mart` al escribir la señal, no evento comercial."
            )
            st.dataframe(
                dfs_display.head(600),
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("Ver detalles técnicos de las señales"):
                st.dataframe(
                    dfs[["signal_type", "entity_kind", "entity_key", "details_json", "score", "created_at"]].head(600),
                    use_container_width=True,
                    hide_index=True,
                )
            return
    finally:
        conn.close()


if __name__ == "__main__":
    main()

