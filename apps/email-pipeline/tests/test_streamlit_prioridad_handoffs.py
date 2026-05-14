"""Contrato de claves y navegación Streamlit (Prioridad del día / handoffs)."""

from __future__ import annotations

import streamlit as st

from origenlab_email_pipeline.streamlit_prioridad_handoffs import (
    SESSION_CI_TODAY_HINT,
    SESSION_LEADS_TODAY_BANNER,
    SESSION_OPP_SIGNAL_FILTER,
    SESSION_BORRADOR_BODY_IN,
    SESSION_BORRADOR_CASE_ID,
    SESSION_BORRADOR_HANDOFF_EMAIL_ID,
    SESSION_BORRADOR_MANUAL_KIND,
    SESSION_BORRADOR_MKT_CONTACT_EMAIL,
    SESSION_BORRADOR_MKT_INST,
    SESSION_BORRADOR_MKT_RECIPIENT,
    SESSION_BORRADOR_MKT_SECTOR,
    SESSION_BORRADOR_MKT_VARIANT,
    SESSION_BORRADOR_NFR,
    SESSION_BORRADOR_ORIGEN_CASO,
    SESSION_BORRADOR_SUBJECT_IN,
    SESSION_BORRADOR_LAST_PKG,
    SESSION_BORRADOR_PICK_EMAIL,
    SESSION_START_PAGE,
    apply_marketing_queue_row_to_borrador_session,
    clear_streamlit_borrador_marketing_prefill,
    navigate_to_page,
)


def test_session_key_literals_stable() -> None:
    assert SESSION_START_PAGE == "start_page"
    assert SESSION_BORRADOR_HANDOFF_EMAIL_ID == "borrador_handoff_email_id"
    assert SESSION_LEADS_TODAY_BANNER == "leads_today_banner"
    assert SESSION_CI_TODAY_HINT == "ci_today_hint"
    assert SESSION_OPP_SIGNAL_FILTER == "opp_signal_filter"


def test_navigate_to_page_sets_start_page_and_flags(monkeypatch) -> None:
    st.session_state.clear()
    called = {"rerun": False}

    def fake_rerun() -> None:
        called["rerun"] = True

    monkeypatch.setattr(st, "rerun", fake_rerun, raising=False)
    navigate_to_page("Organizaciones", org_only_unis=True, extra_flag="x")
    assert called["rerun"] is True
    assert st.session_state[SESSION_START_PAGE] == "Contactos y organizaciones"
    assert st.session_state["org_only_unis"] is True
    assert st.session_state["extra_flag"] == "x"


def test_apply_marketing_queue_row_to_borrador_session_shape() -> None:
    sess: dict[str, object] = {
        SESSION_BORRADOR_LAST_PKG: object(),
        SESSION_BORRADOR_HANDOFF_EMAIL_ID: 9,
        SESSION_BORRADOR_PICK_EMAIL: 8,
    }
    row = {
        "case_id": "c1",
        "institution_name": "Hospital X",
        "recipient_name": "Ana",
        "contact_email": "a@x.cl",
        "sector": "Salud",
        "variant_type": "general",
        "id_lead": 44,
        "fit_bucket": "high_fit",
    }
    apply_marketing_queue_row_to_borrador_session(sess, row=row, default_variant="fallback_v")
    assert SESSION_BORRADOR_LAST_PKG not in sess
    assert SESSION_BORRADOR_HANDOFF_EMAIL_ID not in sess
    assert SESSION_BORRADOR_PICK_EMAIL not in sess
    assert sess[SESSION_BORRADOR_ORIGEN_CASO] == "Entrada manual"
    assert sess[SESSION_BORRADOR_MANUAL_KIND] == "Outreach / presentacion comercial"
    assert sess[SESSION_BORRADOR_CASE_ID] == "c1"
    assert sess[SESSION_BORRADOR_SUBJECT_IN] == "Presentacion OrigenLab | Hospital X"
    assert sess[SESSION_BORRADOR_MKT_RECIPIENT] == "Ana"
    assert sess[SESSION_BORRADOR_MKT_INST] == "Hospital X"
    assert sess[SESSION_BORRADOR_MKT_CONTACT_EMAIL] == "a@x.cl"
    assert sess[SESSION_BORRADOR_MKT_SECTOR] == "Salud"
    assert sess[SESSION_BORRADOR_MKT_VARIANT] == "general"
    assert sess[SESSION_BORRADOR_BODY_IN] == ""
    assert "id_lead=44" in str(sess[SESSION_BORRADOR_NFR])


def test_clear_streamlit_borrador_marketing_prefill() -> None:
    s: dict[str, object] = {
        SESSION_BORRADOR_LAST_PKG: 1,
        SESSION_BORRADOR_HANDOFF_EMAIL_ID: 2,
        SESSION_BORRADOR_PICK_EMAIL: 3,
        SESSION_BORRADOR_NFR: "keep",
    }
    clear_streamlit_borrador_marketing_prefill(s)
    assert SESSION_BORRADOR_LAST_PKG not in s
    assert SESSION_BORRADOR_HANDOFF_EMAIL_ID not in s
    assert SESSION_BORRADOR_PICK_EMAIL not in s
    assert s[SESSION_BORRADOR_NFR] == "keep"
