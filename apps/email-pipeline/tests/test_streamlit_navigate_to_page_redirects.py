"""Regression: navigate_to_page maps legacy menu labels to new sidebar destinations."""

from __future__ import annotations

import streamlit as st

from origenlab_email_pipeline.streamlit_prioridad_handoffs import SESSION_START_PAGE, navigate_to_page


def test_navigate_to_page_redirects_casos_to_seguimientos(monkeypatch):
    st.session_state.clear()
    called = {"rerun": False}

    def fake_rerun() -> None:
        called["rerun"] = True

    monkeypatch.setattr(st, "rerun", fake_rerun, raising=False)
    navigate_to_page("Casos para revisar")
    assert st.session_state[SESSION_START_PAGE] == "Seguimientos y casos"
    assert called["rerun"] is True


def test_navigate_to_page_redirects_resumen_to_inicio(monkeypatch):
    st.session_state.clear()
    monkeypatch.setattr(st, "rerun", lambda: None, raising=False)
    navigate_to_page("Resumen")
    assert st.session_state[SESSION_START_PAGE] == "Inicio"


def test_navigate_to_page_tool_goes_herramientas_with_inner(monkeypatch):
    st.session_state.clear()
    monkeypatch.setattr(st, "rerun", lambda: None, raising=False)
    navigate_to_page("Qué hacer hoy")
    assert st.session_state[SESSION_START_PAGE] == "Herramientas / Runbook"
    assert st.session_state.get("herramienta_inner") == "Qué hacer hoy"
