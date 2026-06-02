"""«Qué hacer hoy»: agrega filas accionables desde colas existentes (neutral module; Streamlit S2).

Orden **explícito y mecánico** (no ranking con ML):
  0 Correos contacto con señal CI positiva
  1 Candidatos comerciales ``needs_review``
  2 Leads high/medium fit sin ``next_action``
  3 Top ``dormant_contact`` en ``opportunity_signals``

Sin escritura en SQLite; ``apply_today_row_handoff`` solo llena claves de sesión (p. ej. Streamlit).
"""

from __future__ import annotations

import sqlite3
from collections.abc import MutableMapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from origenlab_email_pipeline.cases_review_queue import fetch_cases_review_queue
from origenlab_email_pipeline.operational_scope import (
    is_operational_noise_entity,
    sqlite_opportunity_signal_operational_predicate,
)
from origenlab_email_pipeline.lead_export_queries import sql_upstream_active_lead_master
from origenlab_email_pipeline.read.leads_browse import lead_browse_ready

# Must match ``streamlit_prioridad_handoffs`` session key strings.
_SESSION_TODAY_HANDOFF_CASO_EMAIL_ID = "today_handoff_caso_email_id"
_SESSION_CI_ENTITY_KIND = "ci_entity_kind"
_SESSION_CI_STATUS = "ci_status"
_SESSION_CI_TODAY_HINT = "ci_today_hint"
_SESSION_LEADS_TODAY_BANNER = "leads_today_banner"
_SESSION_OPP_SIGNAL_FILTER = "opp_signal_filter"

__all__ = [
    "TodayWorkspaceSpec",
    "TodayWorkspaceRow",
    "gather_today_workspace_rows",
    "sort_today_rows",
    "apply_today_row_handoff",
    "source_label_es",
    "SOURCE_LABEL_ES",
]

HandoffKind = Literal["caso", "ci", "lead", "dormant"]

# Menor número = aparece antes en la lista (más «urgente» en este diseño v1).
TIER_CASO_SENAL_POSITIVA = 0
TIER_CANDIDATO_NEEDS_REVIEW = 1
TIER_LEAD_SIN_NEXT_ACTION = 2
TIER_CUENTA_DORMIDA = 3

TIER_LABELS_ES: dict[int, str] = {
    TIER_CASO_SENAL_POSITIVA: "1 · Correo (contacto) con señal +",
    TIER_CANDIDATO_NEEDS_REVIEW: "2 · Candidato CI · revisión",
    TIER_LEAD_SIN_NEXT_ACTION: "3 · Lead · sin próxima acción",
    TIER_CUENTA_DORMIDA: "4 · Reactivación (cuenta dormida)",
}

# Etiqueta corta en español para la columna «Origen» en la UI (internamente se sigue usando ``source_code`` en tests/handlers).
SOURCE_LABEL_ES: dict[str, str] = {
    "caso": "Correo (contacto)",
    "candidato": "Candidato comercial",
    "lead": "Lead externo",
    "oportunidad": "Cuenta dormida (archivo)",
}


def source_label_es(source_code: str) -> str:
    """Etiqueta en español para mostrar al operador (el código interno no cambia)."""
    return SOURCE_LABEL_ES.get(source_code, source_code)


@dataclass(frozen=True)
class TodayWorkspaceSpec:
    caso_days_window: int = 30
    caso_positive_limit: int = 22
    candidate_limit: int = 36
    candidate_min_confidence: float = 0.45
    lead_limit: int = 32
    dormant_limit: int = 18
    max_total_rows: int = 95
    canonical_only: bool = True


@dataclass(frozen=True)
class TodayWorkspaceRow:
    tier: int
    tier_label_es: str
    source_code: str
    reason_es: str
    reference_es: str
    next_step_es: str
    navigate_page: str
    sort_primary: float
    sort_secondary: str
    handoff_kind: HandoffKind
    handoff_email_id: int | None = None
    handoff_ci_entity_kind: str | None = None
    handoff_ci_entity_key: str | None = None
    handoff_lead_id: int | None = None
    handoff_lead_org: str | None = None

    def to_test_dict(self) -> dict[str, Any]:
        """Serialización estable para tests (sin orden de campos crítico)."""
        d = asdict(self)
        return d


def _fetch_ci_needs_review_slim(
    conn: sqlite3.Connection,
    *,
    min_confidence: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Solo columnas necesarias para «Qué hacer hoy» (evita ``SELECT *``)."""
    if not _table_exists(conn, "v_commercial_candidate_queue"):
        return []
    cap = max(1, min(int(limit), 500))
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT entity_kind, entity_key, display_name, reason_summary, rationale_text,
                   confidence_score, strength_score, updated_at
            FROM v_commercial_candidate_queue
            WHERE status = 'needs_review' AND confidence_score >= ?
            ORDER BY confidence_score DESC, strength_score DESC
            LIMIT ?
            """,
            (float(min_confidence), cap),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.row_factory = prev_factory


def _fetch_leads_today_slim(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    """Leads priorizables sin joins al mart (solo ``lead_master``)."""
    ok, _ = lead_browse_ready(conn)
    if not ok:
        return []
    cap = max(1, min(int(limit), 500))
    up = sql_upstream_active_lead_master("lm")
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            f"""
            SELECT lm.id AS lead_id, lm.org_name, lm.fit_bucket, lm.priority_score, lm.last_seen_at
            FROM lead_master lm
            WHERE {up}
              AND lm.fit_bucket IN ('high_fit', 'medium_fit')
              AND (lm.next_action IS NULL OR TRIM(lm.next_action) = '')
            ORDER BY (lm.priority_score IS NULL), lm.priority_score DESC, lm.id DESC
            LIMIT ?
            """,
            (cap,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.row_factory = prev_factory


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def sort_today_rows(rows: list[TodayWorkspaceRow]) -> list[TodayWorkspaceRow]:
    """Orden dentro de cada tier: ``sort_primary`` descendente, luego ``sort_secondary`` ASC."""
    return sorted(rows, key=lambda r: (r.tier, -r.sort_primary, r.sort_secondary))


def apply_today_row_handoff(row: TodayWorkspaceRow, sess: MutableMapping[str, Any]) -> None:
    """Escribir claves que consumen Casos / Candidatos / Leads / Oportunidades."""
    if row.handoff_kind == "caso" and row.handoff_email_id is not None:
        sess[_SESSION_TODAY_HANDOFF_CASO_EMAIL_ID] = int(row.handoff_email_id)
    elif row.handoff_kind == "ci":
        if row.handoff_ci_entity_kind and row.handoff_ci_entity_key:
            sess[_SESSION_CI_ENTITY_KIND] = row.handoff_ci_entity_kind
            sess[_SESSION_CI_STATUS] = "needs_review"
            sess[_SESSION_CI_TODAY_HINT] = f"{row.handoff_ci_entity_kind} | {row.handoff_ci_entity_key}"
    elif row.handoff_kind == "lead" and row.handoff_lead_id is not None:
        org = row.handoff_lead_org or "—"
        lid = int(row.handoff_lead_id)
        sess[_SESSION_LEADS_TODAY_BANNER] = (
            f"Sugerencia desde **Qué hacer hoy**: revisar lead **{lid}** — {org}. "
            "Use filtros en esta página si no ve la fila."
        )
    elif row.handoff_kind == "dormant":
        sess[_SESSION_OPP_SIGNAL_FILTER] = "dormant_contact"


def _float_metric(value: object, *, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _str_iso(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def gather_today_workspace_rows(
    conn: sqlite3.Connection,
    spec: TodayWorkspaceSpec | None = None,
) -> list[TodayWorkspaceRow]:
    """Recolecta filas de cada fuente disponible, ordena y trunca a ``max_total_rows``."""
    sp = spec or TodayWorkspaceSpec()
    out: list[TodayWorkspaceRow] = []

    # --- Tier 0: casos contacto + señal positiva
    try:
        caso_res = fetch_cases_review_queue(
            conn,
            days_window=int(sp.caso_days_window),
            exclude_obvious_noise=True,
            positive_signal_only=True,
            limit=int(sp.caso_positive_limit),
        )
        for r in caso_res.rows:
            if int(r.get("has_positive_signal") or 0) != 1:
                continue
            eid = int(r["email_id"])
            subj = _str_iso(r.get("subject_preview"))[:72]
            strength = _float_metric(r.get("max_positive_strength"), default=0.0)
            date_s = _str_iso(r.get("date_iso"))[:10]
            out.append(
                TodayWorkspaceRow(
                    tier=TIER_CASO_SENAL_POSITIVA,
                    tier_label_es=TIER_LABELS_ES[TIER_CASO_SENAL_POSITIVA],
                    source_code="caso",
                    reason_es="Mensaje en **Gmail contacto** con señal comercial **positiva** (tabla `commercial_email_signal_fact`).",
                    reference_es=f"Correo ID **{eid}** · {subj or '(sin asunto)'}",
                    next_step_es="Abrir en **Casos para revisar** o redactar en **Borrador comercial**.",
                    navigate_page="Casos para revisar",
                    sort_primary=strength,
                    sort_secondary=date_s,
                    handoff_kind="caso",
                    handoff_email_id=eid,
                )
            )
    except sqlite3.Error:
        pass

    # --- Tier 1: candidatos needs_review
    if _table_exists(conn, "v_commercial_candidate_queue"):
        try:
            ci_rows = _fetch_ci_needs_review_slim(
                conn,
                min_confidence=float(sp.candidate_min_confidence),
                limit=int(sp.candidate_limit),
            )
            for r in ci_rows:
                kind = str(r.get("entity_kind") or "").strip()
                key = str(r.get("entity_key") or "").strip()
                if not kind or not key:
                    continue
                if sp.canonical_only and is_operational_noise_entity(kind, key):
                    continue
                summ = _str_iso(r.get("reason_summary") or r.get("rationale_text"))
                if len(summ) > 220:
                    summ = summ[:217] + "…"
                conf = _float_metric(r.get("confidence_score"))
                strength = _float_metric(r.get("strength_score"))
                updated = _str_iso(r.get("updated_at"))[:19]
                dispn = _str_iso(r.get("display_name"))[:48]
                reason_line = (
                    f"Candidato **pendiente de revisión** "
                    f"(confianza ≥ {sp.candidate_min_confidence:.2f}; "
                    f"conf. {conf:.2f}, intensidad {strength:.2f})."
                )
                if summ:
                    reason_line += f" Resumen: {summ}"
                out.append(
                    TodayWorkspaceRow(
                        tier=TIER_CANDIDATO_NEEDS_REVIEW,
                        tier_label_es=TIER_LABELS_ES[TIER_CANDIDATO_NEEDS_REVIEW],
                        source_code="candidato",
                        reason_es=reason_line,
                        reference_es=f"{kind} · `{key}` · {dispn}",
                        next_step_es="Revisar en **Candidatos comerciales** (aprobar / rechazar / posponer según política).",
                        navigate_page="Candidatos comerciales",
                        sort_primary=conf * max(strength, 0.01),
                        sort_secondary=updated,
                        handoff_kind="ci",
                        handoff_ci_entity_kind=kind,
                        handoff_ci_entity_key=key,
                    )
                )
        except sqlite3.Error:
            pass

    # --- Tier 2: leads high/medium sin next_action (consulta ligera sin joins al mart)
    try:
        lead_rows = _fetch_leads_today_slim(conn, limit=int(sp.lead_limit))
        for d in lead_rows:
            lid = int(d["lead_id"])
            org = _str_iso(d.get("org_name"))[:80] or "—"
            fit = _str_iso(d.get("fit_bucket")) or "—"
            prio = _float_metric(d.get("priority_score"))
            seen = _str_iso(d.get("last_seen_at"))[:10]
            out.append(
                TodayWorkspaceRow(
                    tier=TIER_LEAD_SIN_NEXT_ACTION,
                    tier_label_es=TIER_LABELS_ES[TIER_LEAD_SIN_NEXT_ACTION],
                    source_code="lead",
                    reason_es="Lead **alto o medio encaje** sin «próxima acción» definida en `lead_master` (activo aguas arriba).",
                    reference_es=f"Lead **{lid}** · {org} · encaje **{fit}** · prioridad {prio:.1f}",
                    next_step_es="Definir la próxima acción en **Leads y cuentas** (o en su propio control operativo).",
                    navigate_page="Leads y cuentas",
                    sort_primary=prio,
                    sort_secondary=seen,
                    handoff_kind="lead",
                    handoff_lead_id=lid,
                    handoff_lead_org=org,
                )
            )
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        pass

    # --- Tier 4: dormant signals (canonical Gmail linkage when canonical_only)
    if _table_exists(conn, "opportunity_signals"):
        try:
            dormant_where = "signal_type = 'dormant_contact'"
            if sp.canonical_only and _table_exists(conn, "emails"):
                dormant_where += f" AND {sqlite_opportunity_signal_operational_predicate('os')}"
            cur = conn.execute(
                f"""
                SELECT signal_type, entity_kind, entity_key, score, created_at
                FROM opportunity_signals os
                WHERE {dormant_where}
                ORDER BY score DESC, created_at DESC
                LIMIT ?
                """,
                (int(sp.dormant_limit),),
            )
            cols = [d[0] for d in cur.description] if cur.description else []
            for tup in cur.fetchall():
                d = dict(zip(cols, tup, strict=True))
                ek = str(d.get("entity_key") or "")
                ekind = str(d.get("entity_kind") or "")
                if sp.canonical_only and is_operational_noise_entity(ekind, ek):
                    continue
                score = _float_metric(d.get("score"))
                ct = _str_iso(d.get("created_at"))[:19]
                out.append(
                    TodayWorkspaceRow(
                        tier=TIER_CUENTA_DORMIDA,
                        tier_label_es=TIER_LABELS_ES[TIER_CUENTA_DORMIDA],
                        source_code="oportunidad",
                        reason_es=(
                            "Fila en `opportunity_signals` tipo **dormant_contact** "
                            + (
                                "ligada a **Gmail operativo**."
                                if sp.canonical_only
                                else "(heurística sobre historial/archivo)."
                            )
                        ),
                        reference_es=f"{ekind} · `{ek}` · intensidad **{score:.1f}**",
                        next_step_es="Abrir **Oportunidades** (vista «Cuenta dormida») para contexto y seguimiento.",
                        navigate_page="Oportunidades",
                        sort_primary=score,
                        sort_secondary=ct,
                        handoff_kind="dormant",
                    )
                )
        except sqlite3.Error:
            pass

    sorted_rows = sort_today_rows(out)
    cap = max(5, min(int(sp.max_total_rows), 300))
    return sorted_rows[:cap]
