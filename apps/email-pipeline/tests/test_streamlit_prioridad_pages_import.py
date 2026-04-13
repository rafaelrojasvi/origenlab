"""Smoke import: extractors no deben romper el grafo de importación."""

from __future__ import annotations


def test_streamlit_prioridad_pages_importable() -> None:
    from origenlab_email_pipeline import streamlit_prioridad_pages as m  # noqa: PLC0415

    assert callable(m.render_que_hacer_hoy_page)
    assert callable(m._today_workspace_rows_cached)
