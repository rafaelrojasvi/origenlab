"""Renderers Streamlit del grupo «Prioridad del día» (router vive en ``business_mart_app``)."""

from __future__ import annotations

import io
import json
import sqlite3
from dataclasses import astuple
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from origenlab_email_pipeline.cases_review_queue import (
    commercial_hint_es,
    fetch_case_detail,
    fetch_cases_review_queue,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_email_suppression import fetch_contact_email_suppression_map
from origenlab_email_pipeline.next_marketing_queue import compute_next_marketing_recipients
from origenlab_email_pipeline.streamlit_borrador_support import (
    contact_suppression_reason_label,
    fmt_marketing_variant,
    load_existing_pilot_batch,
    pilot_batch_signature,
)
from origenlab_email_pipeline.streamlit_page_status import render_kpi_metric, render_page_status
from origenlab_email_pipeline.streamlit_prioridad_copy import (
    borrador_visibility_origin_es,
    cases_row_visibility_badges_es,
    marketing_row_visibility_badges_es,
    prioridad_action_hint_es,
    prioridad_hoy_vs_casos_diff_es,
    prioridad_scope_caption_for_page,
    today_row_nav_button_label_es,
    today_row_operational_destination_es,
    today_row_visibility_hint_es,
)
from origenlab_email_pipeline.streamlit_prioridad_handoffs import (
    SESSION_BORRADOR_HANDOFF_EMAIL_ID,
    SESSION_BORRADOR_ORIGEN_CASO,
    SESSION_BORRADOR_PICK_EMAIL,
    SESSION_CASOS_PICK,
    SESSION_TODAY_HANDOFF_CASO_EMAIL_ID,
    apply_marketing_queue_row_to_borrador_session,
    navigate_to_page,
)
from origenlab_email_pipeline.streamlit_today_workspace import (
    TodayWorkspaceRow,
    TodayWorkspaceSpec,
    apply_today_row_handoff,
    gather_today_workspace_rows,
    source_label_es,
)
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    CANONICAL_BASE_PRESENTATION_EMAIL_ES,
    MARKETING_VARIANT_FOLLOWUP,
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_HOSPITALES,
    MARKETING_VARIANT_INDUSTRIA,
    MARKETING_VARIANT_PUBLICO,
    MARKETING_VARIANT_UNIVERSIDADES,
)
from origenlab_email_pipeline.tatiana_copilot.pilot_schemas import extract_asunto_from_draft
from origenlab_email_pipeline.tatiana_copilot.streamlit_draft_helpers import (
    draft_case_from_email_row,
    draft_case_from_manual,
    export_streamlit_review_artifact,
    get_cached_tatiana_index,
    load_contacto_gmail_email_choices_df,
    new_streamlit_export_dir,
    run_origenlab_draft_package,
)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


@st.cache_data(ttl=90, show_spinner=False)
def _cached_gather_today_rows(path_str: str, mtime_ns: int, spec_tuple: tuple[Any, ...]) -> list[dict[str, Any]]:
    spec = TodayWorkspaceSpec(*spec_tuple)
    uri = f"file:{Path(path_str).resolve().as_posix()}?mode=ro&immutable=1"
    c = sqlite3.connect(uri, uri=True, timeout=60.0)
    c.row_factory = sqlite3.Row
    try:
        rows = gather_today_workspace_rows(c, spec)
        return [x.to_test_dict() for x in rows]
    finally:
        c.close()


def _today_workspace_rows_cached(db_path: Path, spec: TodayWorkspaceSpec) -> list[TodayWorkspaceRow]:
    try:
        mt = int(db_path.stat().st_mtime_ns)
    except OSError:
        mt = 0
    raw = _cached_gather_today_rows(str(db_path.resolve()), mt, astuple(spec))
    return [TodayWorkspaceRow(**d) for d in raw]


def render_cases_to_review_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Cola operativa de mensajes Gmail contacto para revisión; entrega a Borrador comercial (sin redactar aquí)."""
    st.subheader("Casos para revisar")
    _scope = prioridad_scope_caption_for_page("Casos para revisar")
    if _scope:
        st.caption(_scope)
    render_page_status(
        "Casos para revisar",
        action_hint=prioridad_action_hint_es("Casos para revisar"),
    )
    st.caption(
        "Una fila = un correo del buzón **Gmail de contacto** en `emails` (no es la bandeja completa ni la cola **`lead_master`**)."
    )
    st.caption(prioridad_hoy_vs_casos_diff_es())
    with st.expander("Qué es esta cola", expanded=False):
        st.caption(
            "Sirve para priorizar mensajes con pistas comerciales. Si activa «solo señal positiva», "
            "hace falta haber corrido la capa de inteligencia comercial v1 sobre este SQLite."
        )
    if not _has_table(conn, "emails"):
        st.error("No se encontró la tabla de mensajes en este archivo.")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        win = st.selectbox(
            "Ventana de fechas",
            options=[7, 30, 90],
            format_func=lambda d: f"Últimos {d} días",
            index=1,
            key="casos_win",
        )
    with c2:
        ex_noise = st.checkbox("Excluir rebotes / avisos de entrega obvios", value=True, key="casos_noise")
    with c3:
        enrich = _has_table(conn, "commercial_email_signal_fact")
        solo_pos = st.checkbox(
            "Solo con señal comercial positiva",
            value=False,
            key="casos_solo_pos",
            disabled=not enrich,
            help="Requiere capa CI v1 (`commercial_email_signal_fact`).",
        )
    with c4:
        lim = st.number_input("Máx. filas", min_value=20, max_value=400, value=150, step=10, key="casos_lim")

    try:
        result = fetch_cases_review_queue(
            conn,
            days_window=int(win),
            exclude_obvious_noise=ex_noise,
            positive_signal_only=solo_pos,
            limit=int(lim),
        )
    except sqlite3.Error as exc:
        st.error(f"No se pudo cargar la cola: {exc}")
        return

    st.caption(result.caption_es)

    if not result.rows:
        st.info("No hay mensajes con los filtros actuales.")
        st.caption(f"Base de datos (solo lectura): `{db_path}`")
        return

    disp = []
    for r in result.rows:
        _state = " · ".join(cases_row_visibility_badges_es(r, enrichment_available=result.enrichment_available))
        disp.append(
            {
                "ID": r["email_id"],
                "Fecha": r.get("date_iso") or "—",
                "Asunto (extracto)": r.get("subject_preview") or "",
                "Remitente (extracto)": r.get("sender_preview") or "",
                "Pista comercial": commercial_hint_es(r, enrichment_available=result.enrichment_available),
                "Estado visible": _state,
            }
        )
    st.dataframe(pd.DataFrame(disp), use_container_width=True, hide_index=True)
    st.caption("**Dónde sigue:** el detalle y la selección son **aquí**; para redactar use el botón hacia **Borrador comercial**.")

    ids = [int(r["email_id"]) for r in result.rows]
    _pre_caso = st.session_state.pop(SESSION_TODAY_HANDOFF_CASO_EMAIL_ID, None)
    if _pre_caso is not None:
        try:
            _pe = int(_pre_caso)
            if _pe in ids:
                st.session_state[SESSION_CASOS_PICK] = _pe
        except (TypeError, ValueError):
            pass

    def _fmt_caso(eid: int) -> str:
        row = next(x for x in result.rows if int(x["email_id"]) == eid)
        sub = str(row.get("subject_preview") or "")[:56]
        return f"ID {eid} · {sub}"

    pick = st.selectbox("Seleccionar caso para ver detalle", ids, format_func=_fmt_caso, key=SESSION_CASOS_PICK)

    det = fetch_case_detail(conn, email_id=int(pick))
    if det:
        st.markdown("#### Detalle del mensaje")
        st.write(
            {
                "Fecha": det.get("date_iso") or "—",
                "Asunto": det.get("subject") or "—",
                "Remitente": det.get("sender") or "—",
                "Origen técnico": det.get("source_file") or "—",
                "Message-ID": det.get("message_id") or "—",
            }
        )
        st.text_area("Vista previa del cuerpo", value=det.get("body_preview") or "(sin cuerpo extraíble)", height=240, disabled=True)
        dc = det.get("document_count")
        if dc is not None:
            st.caption(f"Documentos comerciales ligados a este correo (mart): **{dc}**")
        sigs = det.get("commercial_signals") or []
        if sigs:
            with st.expander("Señales de inteligencia comercial (por mensaje)", expanded=False):
                st.dataframe(pd.DataFrame(sigs), use_container_width=True, hide_index=True)

    if st.button("Abrir Borrador comercial con el caso elegido", type="primary", key="casos_to_borrador"):
        st.session_state[SESSION_BORRADOR_HANDOFF_EMAIL_ID] = int(pick)
        navigate_to_page("Borrador comercial")

    st.caption(f"Base de datos (solo lectura): `{db_path}`")


def render_next_marketing_queue_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Lista operativa de próximos contactos comerciales (sin envío; sin OpenAI aquí)."""
    st.subheader("Cola outreach marketing")
    _scope = prioridad_scope_caption_for_page("Cola outreach marketing")
    if _scope:
        st.caption(_scope)
    render_page_status(
        "Cola outreach marketing",
        action_hint=prioridad_action_hint_es("Cola outreach marketing"),
        note="**No envía correos** y **no llama a OpenAI** en esta pantalla. "
        "Ordena candidatos desde `lead_master` con la **misma** regla de elegibilidad que "
        "`export_marketing_from_contact_master.py` (supresión, Enviados, estados **contacted/replied/snoozed**, "
        "proveedores y ruido según `candidate_export_gate`). No valida “comprador”; use lotes pequeños y revisión humana. "
        "El envío lo hace usted desde Gmail.",
    )
    if not _has_table(conn, "lead_master"):
        st.error("No hay `lead_master` en esta base. Importe o normalice leads antes.")
        st.caption(f"SQLite: `{db_path}`")
        return

    stg = load_settings()
    default_user = (stg.gmail_workspace_user or "contacto@origenlab.cl").strip()
    c1, c2, c3 = st.columns(3)
    with c1:
        limit_n = st.number_input("Filas objetivo (emails únicos)", min_value=1, max_value=500, value=40, step=1)
        fetch_cap = st.number_input("Máx. leads a escanear", min_value=50, max_value=50000, value=4000, step=50)
    with c2:
        gmail_user = st.text_input("Buzón Gmail (Sent / Enviados)", value=default_user)
        include_low = st.checkbox("Incluir low_fit", value=False)
    with c3:
        min_pri_raw = st.text_input("Mín. priority_score (vacío = sin filtro)", value="")
        variant_pick = st.selectbox(
            "Variante por defecto (handoff a borrador)",
            options=[
                MARKETING_VARIANT_GENERAL,
                MARKETING_VARIANT_UNIVERSIDADES,
                MARKETING_VARIANT_HOSPITALES,
                MARKETING_VARIANT_INDUSTRIA,
                MARKETING_VARIANT_PUBLICO,
                MARKETING_VARIANT_FOLLOWUP,
            ],
            format_func=fmt_marketing_variant,
        )

    min_pri: float | None = None
    if (min_pri_raw or "").strip():
        try:
            min_pri = float(min_pri_raw.strip().replace(",", "."))
        except ValueError:
            st.error("Mín. priority_score no es un número válido.")
            return

    try:
        rows, stats = compute_next_marketing_recipients(
            conn,
            gmail_user=gmail_user.strip(),
            limit=int(limit_n),
            fetch_cap=int(fetch_cap),
            include_low_fit=include_low,
            min_priority=min_pri,
            variant_type=variant_pick,
        )
    except sqlite3.Error as exc:
        st.error(f"No se pudo calcular la cola: {exc}")
        return

    render_kpi_metric("Excluidos (Enviados parseados)", f"{stats.n_sent_folder_recipients:,}")
    render_kpi_metric("Suprimidos", f"{stats.n_suppressed:,}", help_text="contact_email_suppression")
    render_kpi_metric(
        "Estado outreach",
        f"{stats.n_outreach_state:,}",
        help_text="Filas distintas en outreach_contact_state con contacted, replied o snoozed (bloquean export)",
    )

    st.caption(
        f"Escaneados **{stats.n_scanned}** filas de `lead_master` · "
        f"Buzón **{stats.gmail_user}** · Meta **{int(limit_n)}** direcciones únicas · "
        f"Obtenidas **{stats.n_kept}**."
    )
    st.caption(
        "Exclusiones aplicadas antes de mostrar filas: historial en Enviados, supresión, estado outreach "
        "(contacted/replied/snoozed), reglas de ruido y dominios proveedor/bloqueados."
    )

    if not rows:
        st.warning("La cola está vacía con estos filtros. Revise emails en leads o use «Incluir low_fit».")
        st.caption(f"SQLite: `{db_path}`")
        return

    df = pd.DataFrame(rows)
    disp = df.rename(
        columns={
            "contact_email": "Email",
            "recipient_name": "Contacto",
            "institution_name": "Institución",
            "sector": "Sector",
            "fit_bucket": "Fit",
            "priority_score": "Prioridad",
            "id_lead": "id_lead",
            "variant_type": "Variante",
        }
    )
    disp["Estado visible"] = [", ".join(marketing_row_visibility_badges_es(r)) for r in rows]
    disp["Siguiente paso"] = "Abrir Borrador comercial (prellenado)"
    show_cols = [c for c in ["Email", "Contacto", "Institución", "Sector", "Fit", "Prioridad", "id_lead", "Variante"] if c in disp.columns]
    show_cols += [c for c in ["Estado visible", "Siguiente paso"] if c in disp.columns]
    st.dataframe(disp[show_cols], use_container_width=True, hide_index=True)
    st.caption("**Dónde sigue:** la tabla es **esta** cola (`lead_master`); el texto del borrador se arma en **Borrador comercial**.")

    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "Descargar cola (CSV)",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name="next_marketing_queue.csv",
        mime="text/csv",
        key="dl_next_mkt_queue",
    )

    labels = [
        f"{r['contact_email']} · {str(r.get('institution_name') or '')[:40]} · id {r['id_lead']}"
        for r in rows
    ]
    pick_idx = st.selectbox("Elegir contacto para prellenar borrador", range(len(labels)), format_func=lambda i: labels[i])
    if st.button("Prellenar y abrir Borrador comercial", type="primary", key="mktq_to_borrador"):
        r = rows[int(pick_idx)]
        apply_marketing_queue_row_to_borrador_session(st.session_state, row=r, default_variant=variant_pick)
        navigate_to_page("Borrador comercial")

    st.caption(
        "El CLI `scripts/leads/export_next_marketing_recipients.py` usa la misma lógica y puede generar "
        "`--pilot-csv` para `run_tatiana_pilot_batch.py` (OpenAI por lote, fuera de Streamlit)."
    )
    st.caption(f"Base de datos (solo lectura): `{db_path}`")


def render_commercial_draft_review_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """OrigenLab-mode drafting for human review only (no send; optional filesystem export under reports/out)."""
    _handoff = st.session_state.pop(SESSION_BORRADOR_HANDOFF_EMAIL_ID, None)
    if _handoff is not None:
        st.session_state[SESSION_BORRADOR_ORIGEN_CASO] = "Correo reciente (Gmail contacto)"
        st.session_state[SESSION_BORRADOR_PICK_EMAIL] = int(_handoff)

    st.subheader("Borrador comercial (revisión)")
    _scope = prioridad_scope_caption_for_page("Borrador comercial")
    if _scope:
        st.caption(_scope)
    render_page_status(
        "Borrador comercial",
        action_hint=prioridad_action_hint_es("Borrador comercial"),
        note="No envía correos. Aquí puede revisar borradores guardados o crear uno nuevo y guardar el resultado en archivos.",
    )
    st.caption(
        "**Solo revisión humana:** no envía correos, no escribe en el buzón y no modifica filas en la tabla de correos. "
        "Modo **OrigenLab** siempre. El texto exacto del mensaje puede ingresarse a mano o tomarse del archivo de correos "
        "(**Gmail** de contacto); el resto de tablas de negocio es contexto indirecto, no la fuente única del texto."
    )

    settings = load_settings()
    st.markdown("### Revisar borradores guardados")
    st.caption("Abra una carpeta ya generada para revisar textos, emails de contacto y metadatos del batch.")
    default_batch_dir = str(settings.resolved_reports_dir() / "latest_tatiana_pilot_batch")
    batch_dir_in = st.text_input(
        "Carpeta de batch existente",
        value=default_batch_dir,
        key="borrador_existing_batch_dir",
        help="Puede usar la carpeta exacta del batch o el symlink `latest_tatiana_pilot_batch`.",
    )
    current_batch_sig = pilot_batch_signature(batch_dir_in)
    loaded_batch_dir = str(st.session_state.get("borrador_existing_batch_dir_loaded") or "")
    loaded_batch_sig = st.session_state.get("borrador_existing_batch_sig")
    if st.button("Cargar batch existente", key="borrador_load_existing_batch"):
        df_batch, cases_batch, err = load_existing_pilot_batch(batch_dir_in)
        if err:
            st.error(err)
        else:
            st.session_state["borrador_existing_batch_df"] = df_batch
            st.session_state["borrador_existing_batch_cases"] = cases_batch
            st.session_state["borrador_existing_batch_dir_loaded"] = batch_dir_in
            st.session_state["borrador_existing_batch_sig"] = current_batch_sig
            st.success("Batch cargado para revisión.")
    elif loaded_batch_dir == batch_dir_in and current_batch_sig and current_batch_sig != loaded_batch_sig:
        df_batch, cases_batch, err = load_existing_pilot_batch(batch_dir_in)
        if not err:
            st.session_state["borrador_existing_batch_df"] = df_batch
            st.session_state["borrador_existing_batch_cases"] = cases_batch
            st.session_state["borrador_existing_batch_sig"] = current_batch_sig
            st.info("Se recargó el batch porque cambió su contenido en disco.")

    df_batch = st.session_state.get("borrador_existing_batch_df")
    cases_batch = st.session_state.get("borrador_existing_batch_cases")
    if isinstance(df_batch, pd.DataFrame) and cases_batch:
        with st.expander("Ver drafts ya generados", expanded=True):
            show = df_batch.copy()
            batch_supp_map: dict[str, dict[str, object]] = {}
            if "case_id" in show.columns:
                case_email_map: dict[str, str] = {}
                for obj in cases_batch:
                    case = dict(obj.get("case") or {})
                    cid = str(case.get("case_id") or "")
                    meta = dict(case.get("context_metadata") or {})
                    email = str(meta.get("contact_email") or "").strip()
                    if cid and email:
                        case_email_map[cid] = email
                if case_email_map:
                    show["contact_email"] = show["case_id"].map(case_email_map).fillna("")
                    batch_supp_map = fetch_contact_email_suppression_map(conn, list(case_email_map.values()))
                    if batch_supp_map:
                        show["email_suppressed"] = show["contact_email"].map(
                            lambda x: "Sí" if str(x).strip().lower() in batch_supp_map else ""
                        )
            rename_map = {
                "case_id": "Caso",
                "contact_email": "Email contacto",
                "email_suppressed": "Rebotado / bloqueado",
                "subject_input": "Asunto entrada",
                "generated_subject": "Asunto generado",
                "abstained": "¿Abstuvo?",
                "provider_name": "Proveedor",
                "system_notes": "Notas sistema",
                "reviewer_decision": "Decision",
                "reviewer_notes": "Notas revisor",
            }
            keep_cols = [c for c in rename_map.keys() if c in show.columns]
            st.dataframe(show[keep_cols].rename(columns=rename_map), use_container_width=True, hide_index=True)
            case_labels = []
            case_index: dict[str, dict[str, Any]] = {}
            for obj in cases_batch:
                case = dict(obj.get("case") or {})
                cid = str(case.get("case_id") or obj.get("_case_file") or "case")
                subj = str(case.get("subject") or "")[:72]
                label = f"{cid} · {subj}" if subj else cid
                case_labels.append(label)
                case_index[label] = obj
            if case_labels:
                picked = st.selectbox("Elegir draft del batch", options=case_labels, key="borrador_existing_case_pick")
                chosen = case_index[picked]
                case = dict(chosen.get("case") or {})
                selected_case_key = str(case.get("case_id") or chosen.get("_case_file") or "case")
                chosen_email = str((case.get("context_metadata") or {}).get("contact_email") or "").strip().lower()
                chosen_supp = batch_supp_map.get(chosen_email) if chosen_email else None
                st.markdown("#### Caso original")
                st.write(
                    {
                        "case_id": case.get("case_id") or "—",
                        "subject": case.get("subject") or "—",
                        "expected_label": case.get("expected_label") or "—",
                        "archivo_json": chosen.get("_case_file") or "—",
                    }
                )
                if chosen_email:
                    st.caption(f"Email de contacto: `{chosen_email}`")
                if chosen_supp:
                    st.warning(
                        "Este email está marcado para no reutilizarse: "
                        f"{contact_suppression_reason_label(str(chosen_supp.get('suppression_reason_code') or ''))}."
                    )
                st.text_area(
                    "Contexto / briefing del caso",
                    value=str(case.get("body_text") or ""),
                    height=220,
                    disabled=True,
                    key=f"borrador_existing_case_body_{selected_case_key}",
                )
                st.markdown("#### Draft generado")
                st.text_area(
                    "Texto del draft",
                    value=str(chosen.get("generated_draft") or ""),
                    height=320,
                    disabled=True,
                    key=f"borrador_existing_generated_{selected_case_key}",
                )
                with st.expander("Metadata y referencias del package", expanded=False):
                    st.json(
                        {
                            "prompt_blocks": chosen.get("prompt_blocks"),
                            "guardrails": chosen.get("guardrails"),
                            "retrieved_style_examples": chosen.get("retrieved_style_examples"),
                            "retrieved_examples": chosen.get("retrieved_examples"),
                            "notes": chosen.get("notes"),
                            "provider_name": chosen.get("provider_name"),
                            "abstained": chosen.get("abstained"),
                        }
                    )
                st.download_button(
                    "Descargar case JSON del batch",
                    data=json.dumps(chosen, ensure_ascii=False, indent=2),
                    file_name=str(chosen.get("_case_file") or "case.json"),
                    mime="application/json",
                    key="borrador_existing_dl_case",
                )

    st.divider()
    st.markdown("### Crear nuevo borrador")
    st.caption("Elija si quiere partir desde un correo reciente de Gmail contacto o desde una entrada manual/outreach.")
    mode = st.radio(
        "Origen del caso",
        ("Entrada manual", "Correo reciente (Gmail contacto)"),
        horizontal=True,
        key="borrador_origen_caso",
    )
    st.caption(
        borrador_visibility_origin_es(
            mode=str(mode),
            manual_kind=str(st.session_state.get("borrador_manual_kind") or ""),
        )
    )

    _GEN_OPENAI_LABEL = "OpenAI (requiere API configurada)"
    _GEN_SIM_LABEL = "Simulación sin API (solo prueba, sin costo)"

    selected_email_id: int | None = None
    if mode == "Entrada manual":
        draft_kind = st.radio(
            "Tipo de borrador manual",
            ("Respuesta comercial / caso puntual", "Outreach / presentacion comercial"),
            horizontal=True,
            key="borrador_manual_kind",
        )
        st.text_input("Identificador del caso", value="streamlit_manual_001", key="borrador_case_id")
        if draft_kind == "Outreach / presentacion comercial":
            st.text_input("Asunto sugerido", value="Presentacion OrigenLab", key="borrador_subject_in")
            st.caption(
                "Modo review-first para correos de presentacion. Si deja el cuerpo vacio, la app arma una base "
                "canonica y la envia al modelo con los campos de personalizacion confirmados."
            )
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Nombre del destinatario (opcional)", key="borrador_mkt_recipient")
                st.text_input("Institucion / empresa (opcional)", key="borrador_mkt_inst")
                st.text_input("Correo del contacto (solo registro, opcional)", key="borrador_mkt_contact_email")
                st.selectbox(
                    "Variante",
                    options=[
                        MARKETING_VARIANT_GENERAL,
                        MARKETING_VARIANT_UNIVERSIDADES,
                        MARKETING_VARIANT_HOSPITALES,
                        MARKETING_VARIANT_INDUSTRIA,
                        MARKETING_VARIANT_PUBLICO,
                        MARKETING_VARIANT_FOLLOWUP,
                    ],
                    format_func=fmt_marketing_variant,
                    key="borrador_mkt_variant",
                )
            with c2:
                st.text_input("Sector (opcional)", key="borrador_mkt_sector")
                st.text_input("Foco de producto (opcional)", key="borrador_mkt_product_focus")
                st.text_input("Caso de uso probable (opcional)", key="borrador_mkt_use_case")
                st.text_area("Nota personalizada confirmada (opcional)", height=90, key="borrador_mkt_custom_note")
            st.text_area(
                "Cuerpo base / briefing adicional (opcional)",
                height=180,
                key="borrador_body_in",
                help="Opcional. Si lo deja vacio, se usa una base canonica de presentacion OrigenLab y los campos confirmados.",
            )
            st.text_area("Notas internas para quien revisa (opcional)", height=70, key="borrador_nfr")
            with st.expander("Base canonica de presentacion usada como referencia", expanded=False):
                st.text_area(
                    "Referencia",
                    value=CANONICAL_BASE_PRESENTATION_EMAIL_ES,
                    height=180,
                    disabled=True,
                )
        else:
            st.text_input("Asunto del mensaje entrante", key="borrador_subject_in")
            st.text_area("Cuerpo del mensaje entrante", height=220, key="borrador_body_in")
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Nombre del solicitante (opcional)", key="borrador_rn")
                st.text_input("Correo del solicitante (opcional)", key="borrador_re")
                st.text_input("Producto o categoría solicitada (opcional)", key="borrador_rpc")
            with c2:
                st.text_area("Hechos ya confirmados (opcional)", height=90, key="borrador_ekf")
                st.text_area("Información que aún falta (opcional)", height=90, key="borrador_mi")
            st.text_area("Notas internas para quien revisa (opcional)", height=70, key="borrador_nfr")
    else:
        if not _has_table(conn, "emails"):
            st.error("No se encontró la tabla de mensajes de correo en este archivo.")
            return
        try:
            _ensure = st.session_state.get("borrador_pick_email")
            _ensure_ids = [int(_ensure)] if _ensure is not None else None
            pick_df = load_contacto_gmail_email_choices_df(
                conn, limit=200, ensure_email_ids=_ensure_ids
            )
        except Exception as exc:
            st.error(f"No se pudieron leer los mensajes: {exc}")
            return
        if pick_df.empty:
            st.warning(
                "No hay correos del buzón **Gmail de contacto** en el archivo. "
                "Puede importarlos con el script de Gmail (Workspace) o usar entrada manual."
            )
            return
        _cols_es = {
            "id": "ID",
            "date_iso": "Fecha",
            "subject_preview": "Asunto (extracto)",
            "sender_preview": "Remitente (extracto)",
            "source_file": "Origen técnico",
        }
        st.dataframe(
            pick_df.rename(columns={k: v for k, v in _cols_es.items() if k in pick_df.columns}),
            use_container_width=True,
            hide_index=True,
        )
        ids = [int(x) for x in pick_df["id"].tolist()]

        def _fmt_row(eid: int) -> str:
            row = pick_df.loc[pick_df["id"] == eid].iloc[0]
            subj = str(row.get("subject_preview") or "")
            ds = str(row.get("date_iso") or "")
            return f"{ds} · {subj[:72]} · ID {eid}"

        selected_email_id = st.selectbox("Elegir un correo de la lista", ids, format_func=_fmt_row, key="borrador_pick_email")

    gen_mode = st.radio(
        "Motor de generación",
        (_GEN_OPENAI_LABEL, _GEN_SIM_LABEL),
        horizontal=True,
        key="borrador_gen_mode",
        help="Si no elige simulación, se usa OpenAI; si falta la clave de API, verá un mensaje de error claro (sin cambiar solo a modo simulado).",
    )
    use_mock = gen_mode == _GEN_SIM_LABEL

    _btn_label = (
        "Generar borrador de outreach (OrigenLab)"
        if mode == "Entrada manual"
        and st.session_state.get("borrador_manual_kind") == "Outreach / presentacion comercial"
        else "Generar borrador (OrigenLab)"
    )
    if st.button(_btn_label, type="primary", key="borrador_gen_btn"):
        try:
            if mode == "Entrada manual":
                body_raw = (st.session_state.get("borrador_body_in") or "").strip()
                is_outreach = st.session_state.get("borrador_manual_kind") == "Outreach / presentacion comercial"
                if not body_raw and not is_outreach:
                    st.error("El cuerpo del mensaje entrante es obligatorio.")
                else:
                    case = draft_case_from_manual(
                        case_id=str(st.session_state.get("borrador_case_id") or "streamlit_manual_case"),
                        subject=str(st.session_state.get("borrador_subject_in") or ""),
                        body_text=body_raw,
                        requester_name=(st.session_state.get("borrador_rn") or "").strip() or None,
                        requester_email=(st.session_state.get("borrador_re") or "").strip() or None,
                        requested_product_or_category=(st.session_state.get("borrador_rpc") or "").strip() or None,
                        explicit_known_facts=(st.session_state.get("borrador_ekf") or "").strip() or None,
                        missing_information=(st.session_state.get("borrador_mi") or "").strip() or None,
                        notes_for_reviewer=(st.session_state.get("borrador_nfr") or "").strip() or None,
                        recipient_name=(st.session_state.get("borrador_mkt_recipient") or "").strip() or None,
                        institution_name=(st.session_state.get("borrador_mkt_inst") or "").strip() or None,
                        sector=(st.session_state.get("borrador_mkt_sector") or "").strip() or None,
                        product_focus=(st.session_state.get("borrador_mkt_product_focus") or "").strip() or None,
                        use_case=(st.session_state.get("borrador_mkt_use_case") or "").strip() or None,
                        variant_type=(st.session_state.get("borrador_mkt_variant") or "").strip() or None,
                        contact_email=(st.session_state.get("borrador_mkt_contact_email") or "").strip() or None,
                        custom_note=(st.session_state.get("borrador_mkt_custom_note") or "").strip() or None,
                        marketing_outreach=is_outreach,
                    )
                    index = get_cached_tatiana_index(settings, st.session_state)
                    pkg = run_origenlab_draft_package(
                        case=case,
                        settings=settings,
                        index=index,
                        generator_name="openai_chat",
                        use_mock_explicit=use_mock,
                    )
                    st.session_state["borrador_last_pkg"] = pkg
            else:
                if selected_email_id is None:
                    st.error("Seleccione un correo de la lista.")
                else:
                    case = draft_case_from_email_row(conn, email_id=selected_email_id)
                    if case is None:
                        st.error("No se encontró el correo seleccionado.")
                    else:
                        index = get_cached_tatiana_index(settings, st.session_state)
                        pkg = run_origenlab_draft_package(
                            case=case,
                            settings=settings,
                            index=index,
                            generator_name="openai_chat",
                            use_mock_explicit=use_mock,
                        )
                        st.session_state["borrador_last_pkg"] = pkg
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.exception(exc)

    pkg = st.session_state.get("borrador_last_pkg")
    if not pkg:
        st.info("Pulse **Generar borrador (OrigenLab)** arriba para ver el resultado y los campos de revisión.")
        st.caption(f"Base de datos (solo lectura): `{db_path}`")
        return

    gen_subject = extract_asunto_from_draft(pkg.generated_draft or "")
    st.markdown("### Borrador generado")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("¿Se abstuvo el modelo?", "Sí" if pkg.abstained else "No")
    with c2:
        st.metric("Proveedor técnico", pkg.provider_name or "—")
    with c3:
        st.metric("Asunto sugerido (1.ª línea)", gen_subject[:80] + ("…" if len(gen_subject) > 80 else ""))

    st.text_area("Texto completo del borrador", value=pkg.generated_draft or "", height=320, disabled=True)

    st.markdown("#### Ejemplos usados como referencia (estilo y precedentes)")
    st.write(
        "**Identificadores de estilo:** "
        + ", ".join(str(x.get("example_id", "")) for x in pkg.retrieved_style_examples)
        + "  \n**Identificadores de precedentes:** "
        + ", ".join(str(x.get("example_id", "")) for x in pkg.retrieved_examples)
    )

    blocks = pkg.prompt_blocks or {}
    with st.expander("Hechos de empresa y política comercial (resumen)", expanded=False):
        st.json(
            {
                "hechos_empresa": blocks.get("company_facts"),
                "politica_comercial": blocks.get("commercial_policy"),
                "firma_aprobada": blocks.get("approved_signature_block"),
                "fuentes_de_hechos": blocks.get("origenlab_fact_sources"),
                "complemento_del_caso": blocks.get("case_context_supplement"),
                "marketing_outreach": blocks.get("marketing_outreach_supplement"),
            }
        )
    with st.expander("Límites y reglas enviadas al modelo", expanded=False):
        st.caption("El sistema usa este texto en **inglés** al generar el borrador (convención técnica).")
        for g in pkg.guardrails or []:
            st.write(f"- {g}")

    st.download_button(
        "Descargar paquete (archivo JSON)",
        data=json.dumps(pkg.to_dict(), ensure_ascii=False, indent=2),
        file_name="borrador_paquete.json",
        mime="application/json",
        key="borrador_dl_json",
    )

    st.markdown("### Revisión humana (solo en pantalla o al exportar)")
    st.caption(
        "En el archivo exportado, el campo de «aprobado para envío» queda siempre en **no**; esta aplicación **no envía** correos."
    )

    decision_labels = {
        "": "(sin decidir)",
        "approve": "Aprobar",
        "approve_with_edits": "Aprobar con ediciones",
        "reject": "Rechazar",
        "needs_clarification": "Falta información del cliente",
    }
    rev_decision = st.selectbox(
        "Decisión del revisor",
        options=list(decision_labels.keys()),
        format_func=lambda k: decision_labels[k],
        key="borrador_rev_decision",
    )
    rev_notes = st.text_area("Comentarios del revisor", key="borrador_rev_notes")
    rev_subj = st.text_input("Asunto final (tras revisión)", value=gen_subject, key="borrador_rev_subj")
    rev_body = st.text_area("Cuerpo final (tras revisión)", value=pkg.generated_draft or "", height=200, key="borrador_rev_body")

    if st.button("Guardar revisión en carpeta de informes (reports/out)", key="borrador_export_btn"):
        try:
            out_dir = new_streamlit_export_dir(settings)
            info = export_streamlit_review_artifact(
                out_dir=out_dir,
                pkg=pkg,
                reviewer_decision=rev_decision,
                reviewer_notes=rev_notes,
                reviewer_final_subject=rev_subj,
                reviewer_final_body=rev_body,
            )
            st.success(
                f"Guardado en `{info['out_dir']}`: paquete JSON, tabla de revisión (CSV) y copia del contexto OrigenLab."
            )
        except OSError as exc:
            st.error(f"No se pudo guardar en el disco: {exc}")

    st.caption(f"Base de datos (solo lectura): `{db_path}`")


def render_que_hacer_hoy_page(conn: sqlite3.Connection, db_path: Path) -> None:
    """Workspace compacto: colas existentes, orden explícito, sin ranking opaco."""
    st.subheader("Qué hacer hoy")
    _scope = prioridad_scope_caption_for_page("Qué hacer hoy")
    if _scope:
        st.caption(_scope)
    render_page_status(
        "Qué hacer hoy",
        action_hint=prioridad_action_hint_es("Qué hacer hoy"),
        note="Cada tarjeta viene de **una** cola SQL distinta. El botón abre la **página del menú** que corresponde "
        "(Casos para revisar, Candidatos comerciales, Leads y cuentas u Oportunidades); **no** mezcla fuentes en una sola cola detrás de escena.",
    )
    st.info(
        "Vista **resumen** del grupo «Prioridad del día»: lista filas de **varias fuentes** en un solo panel para orientarse. "
        "Cada fila indica **origen**, **motivo** y **siguiente paso**; la acción la ejecuta usted en la página destino."
    )
    st.caption(
        "Sugerencias del día reunidas en un solo lugar. Cada fila dice **de dónde viene** y **por qué está acá**. "
        "No ejecuta acciones sola: solo orienta."
    )
    st.caption(prioridad_hoy_vs_casos_diff_es())
    spec = TodayWorkspaceSpec()
    rows = _today_workspace_rows_cached(db_path, spec)
    with st.expander("Cómo funciona esta vista", expanded=False):
        st.markdown(
            """
Las filas siguen un **orden fijo** (no es una IA que «adivina» prioridades):

1. **Correos de contacto** con señal comercial positiva (capa CI en el mensaje).
2. **Candidatos** marcados como pendientes de revisión, con confianza sobre un mínimo.
3. **Leads** de encaje alto o medio **sin** próxima acción escrita.
4. **Cuentas dormidas** detectadas en el mart (señal heurística).

Dentro de cada grupo el orden es numérico y transparente (fechas o puntajes ya guardados en la base). \
Se limita la cantidad de filas para que la pantalla sea usable. **No se cruzan ni fusionan** duplicados entre fuentes en esta versión.
            """
        )
        st.caption(
            "Los datos se actualizan al recargar la página; la caché de unos segundos solo evita repetir lecturas "
            "si la base no cambió en el disco."
        )

    if not rows:
        st.info(
            "Por ahora no hay filas que cumplan los criterios, o faltan datos/tablas en este SQLite "
            "(correos con CI, leads, oportunidades). Revise **Salud de datos** y el runbook de pipelines."
        )
        st.caption(f"Base: `{db_path}`")
        return

    st.caption(f"Hasta **{len(rows)}** sugerencias · `{db_path}`")

    for i, r in enumerate(rows):
        _src_es = source_label_es(r.source_code)
        with st.container():
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"**{r.tier_label_es}** · Origen: **{_src_es}**")
                st.write(f"**Referencia:** {r.reference_es}")
                st.caption(r.reason_es)
                st.caption(f"**Siguiente paso (texto de la cola de origen):** {r.next_step_es}")
                st.caption(today_row_visibility_hint_es(r.source_code, r.navigate_page))
                st.caption(today_row_operational_destination_es(r.navigate_page))
            with c2:
                if st.button(today_row_nav_button_label_es(r.navigate_page), key=f"today_go_{i}"):
                    apply_today_row_handoff(r, st.session_state)
                    navigate_to_page(r.navigate_page)
        if i < len(rows) - 1:
            st.divider()


__all__ = [
    "render_cases_to_review_page",
    "render_next_marketing_queue_page",
    "render_commercial_draft_review_page",
    "render_que_hacer_hoy_page",
    "_today_workspace_rows_cached",
    "_cached_gather_today_rows",
]
