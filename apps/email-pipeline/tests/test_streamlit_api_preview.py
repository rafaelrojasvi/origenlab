"""Phase 5F: optional Streamlit API preview page removed."""

from __future__ import annotations

from pathlib import Path

from origenlab_email_pipeline.streamlit_page_status import PAGE_STATUS_PRESETS

REPO = Path(__file__).resolve().parents[1]
APP_SOURCE = (REPO / "apps" / "business_mart_app.py").read_text(encoding="utf-8")
MODULE_PATH = REPO / "src" / "origenlab_email_pipeline" / "streamlit_api_preview.py"


def test_phase5f_streamlit_api_preview_module_removed() -> None:
    assert not MODULE_PATH.is_file()


def test_business_mart_app_has_no_api_preview_wiring() -> None:
    assert "streamlit_api_preview" not in APP_SOURCE
    assert "render_api_preview_page" not in APP_SOURCE
    assert 'page == "API preview"' not in APP_SOURCE
    assert "API preview" not in APP_SOURCE


def test_page_status_presets_exclude_api_preview() -> None:
    assert "API preview" not in PAGE_STATUS_PRESETS
