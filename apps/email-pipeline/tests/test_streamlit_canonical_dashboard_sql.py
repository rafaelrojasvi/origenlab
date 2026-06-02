"""Phase 5G: Streamlit-named canonical SQL shim removed."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_SOURCE = (REPO / "apps" / "business_mart_app.py").read_text(encoding="utf-8")
MODULE_PATH = REPO / "src" / "origenlab_email_pipeline" / "streamlit_canonical_dashboard_sql.py"


def test_phase5g_streamlit_canonical_dashboard_sql_module_removed() -> None:
    assert not MODULE_PATH.is_file()


def test_business_mart_app_imports_canonical_operational_sql() -> None:
    assert "streamlit_canonical_dashboard_sql" not in APP_SOURCE
    assert "canonical_operational_sql" in APP_SOURCE


def test_canonical_operational_sql_module_exists() -> None:
    canonical_path = REPO / "src" / "origenlab_email_pipeline" / "canonical_operational_sql.py"
    assert canonical_path.is_file()
