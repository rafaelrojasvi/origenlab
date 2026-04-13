"""Contrato de handoff y navegación Streamlit (Prioridad del día y vistas relacionadas).

Centraliza nombres de claves en ``st.session_state`` y la función de navegación usada
por el mart operator. No altera reglas de negocio: solo agrupa lo que ya existía.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

# --- Navegación global (todas las páginas del mart app) ---
SESSION_START_PAGE = "start_page"


def navigate_to_page(page: str, **flags: object) -> None:
    """Actualizar session_state para navegación guiada y forzar recarga (mismo contrato que antes)."""
    st.session_state[SESSION_START_PAGE] = page
    for k, v in flags.items():
        st.session_state[k] = v
    try:
        st.rerun()
    except AttributeError:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()


# --- Qué hacer hoy → otras vistas ---
SESSION_TODAY_HANDOFF_CASO_EMAIL_ID = "today_handoff_caso_email_id"
SESSION_CI_ENTITY_KIND = "ci_entity_kind"
SESSION_CI_STATUS = "ci_status"
SESSION_CI_TODAY_HINT = "ci_today_hint"
SESSION_LEADS_TODAY_BANNER = "leads_today_banner"
SESSION_OPP_SIGNAL_FILTER = "opp_signal_filter"


# --- Casos para revisar ↔ Borrador ---
SESSION_BORRADOR_HANDOFF_EMAIL_ID = "borrador_handoff_email_id"
SESSION_CASOS_PICK = "casos_pick"


# --- Cola outreach → Borrador (mismas claves que ya consumía Borrador comercial) ---
SESSION_BORRADOR_LAST_PKG = "borrador_last_pkg"
SESSION_BORRADOR_PICK_EMAIL = "borrador_pick_email"
SESSION_BORRADOR_ORIGEN_CASO = "borrador_origen_caso"
SESSION_BORRADOR_MANUAL_KIND = "borrador_manual_kind"
SESSION_BORRADOR_CASE_ID = "borrador_case_id"
SESSION_BORRADOR_SUBJECT_IN = "borrador_subject_in"
SESSION_BORRADOR_MKT_RECIPIENT = "borrador_mkt_recipient"
SESSION_BORRADOR_MKT_INST = "borrador_mkt_inst"
SESSION_BORRADOR_MKT_CONTACT_EMAIL = "borrador_mkt_contact_email"
SESSION_BORRADOR_MKT_SECTOR = "borrador_mkt_sector"
SESSION_BORRADOR_MKT_VARIANT = "borrador_mkt_variant"
SESSION_BORRADOR_MKT_PRODUCT_FOCUS = "borrador_mkt_product_focus"
SESSION_BORRADOR_MKT_USE_CASE = "borrador_mkt_use_case"
SESSION_BORRADOR_MKT_CUSTOM_NOTE = "borrador_mkt_custom_note"
SESSION_BORRADOR_BODY_IN = "borrador_body_in"
SESSION_BORRADOR_NFR = "borrador_nfr"


def clear_streamlit_borrador_marketing_prefill(sess: Any) -> None:
    """Quitar paquetes previos y selección de correo Gmail antes de un handoff desde outreach."""
    sess.pop(SESSION_BORRADOR_LAST_PKG, None)
    sess.pop(SESSION_BORRADOR_HANDOFF_EMAIL_ID, None)
    sess.pop(SESSION_BORRADOR_PICK_EMAIL, None)


def apply_marketing_queue_row_to_borrador_session(
    sess: Any,
    *,
    row: dict[str, Any],
    default_variant: str,
) -> None:
    """Rellenar session_state como el botón «Prellenar y abrir Borrador comercial (outreach)» ya hacía."""
    clear_streamlit_borrador_marketing_prefill(sess)
    inst = str(row.get("institution_name") or "").strip()
    sess[SESSION_BORRADOR_ORIGEN_CASO] = "Entrada manual"
    sess[SESSION_BORRADOR_MANUAL_KIND] = "Outreach / presentacion comercial"
    sess[SESSION_BORRADOR_CASE_ID] = str(row.get("case_id") or "")
    sess[SESSION_BORRADOR_SUBJECT_IN] = f"Presentacion OrigenLab | {inst}" if inst else "Presentacion OrigenLab"
    sess[SESSION_BORRADOR_MKT_RECIPIENT] = str(row.get("recipient_name") or "")
    sess[SESSION_BORRADOR_MKT_INST] = str(row.get("institution_name") or "")
    sess[SESSION_BORRADOR_MKT_CONTACT_EMAIL] = str(row.get("contact_email") or "")
    sess[SESSION_BORRADOR_MKT_SECTOR] = str(row.get("sector") or "")
    sess[SESSION_BORRADOR_MKT_VARIANT] = str(row.get("variant_type") or default_variant)
    sess[SESSION_BORRADOR_MKT_PRODUCT_FOCUS] = ""
    sess[SESSION_BORRADOR_MKT_USE_CASE] = ""
    sess[SESSION_BORRADOR_MKT_CUSTOM_NOTE] = ""
    sess[SESSION_BORRADOR_BODY_IN] = ""
    sess[SESSION_BORRADOR_NFR] = f"id_lead={row.get('id_lead')} fit={row.get('fit_bucket')} · cola outreach"


__all__ = [
    "SESSION_START_PAGE",
    "navigate_to_page",
    "SESSION_TODAY_HANDOFF_CASO_EMAIL_ID",
    "SESSION_CI_ENTITY_KIND",
    "SESSION_CI_STATUS",
    "SESSION_CI_TODAY_HINT",
    "SESSION_LEADS_TODAY_BANNER",
    "SESSION_OPP_SIGNAL_FILTER",
    "SESSION_BORRADOR_HANDOFF_EMAIL_ID",
    "SESSION_CASOS_PICK",
    "SESSION_BORRADOR_LAST_PKG",
    "SESSION_BORRADOR_PICK_EMAIL",
    "SESSION_BORRADOR_ORIGEN_CASO",
    "SESSION_BORRADOR_MANUAL_KIND",
    "SESSION_BORRADOR_CASE_ID",
    "SESSION_BORRADOR_SUBJECT_IN",
    "SESSION_BORRADOR_MKT_RECIPIENT",
    "SESSION_BORRADOR_MKT_INST",
    "SESSION_BORRADOR_MKT_CONTACT_EMAIL",
    "SESSION_BORRADOR_MKT_SECTOR",
    "SESSION_BORRADOR_MKT_VARIANT",
    "SESSION_BORRADOR_MKT_PRODUCT_FOCUS",
    "SESSION_BORRADOR_MKT_USE_CASE",
    "SESSION_BORRADOR_MKT_CUSTOM_NOTE",
    "SESSION_BORRADOR_BODY_IN",
    "SESSION_BORRADOR_NFR",
    "clear_streamlit_borrador_marketing_prefill",
    "apply_marketing_queue_row_to_borrador_session",
]
