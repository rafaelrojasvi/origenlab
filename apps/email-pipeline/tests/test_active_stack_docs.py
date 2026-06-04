"""Docs guardrail: active stack vs Streamlit retirement plan is present and explicit."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PLAN = _REPO / "docs/audits/ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md"
_LAUNCH_PLAN = _REPO / "docs/audits/STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md"


def test_active_stack_retirement_plan_exists() -> None:
    assert _PLAN.is_file(), f"missing plan doc: {_PLAN}"


def test_active_stack_retirement_plan_covers_required_terms() -> None:
    text = _PLAN.read_text(encoding="utf-8")
    required = (
        "apps/dashboard",
        "apps/api",
        "Postgres mirror",
        "Streamlit",
        "legacy",
        "parked",
    )
    for term in required:
        assert term in text, f"plan doc must mention {term!r}"


def test_streamlit_launch_surface_removal_plan_exists() -> None:
    assert _LAUNCH_PLAN.is_file()


def test_launch_plan_documents_lan_launcher_removal() -> None:
    text = _LAUNCH_PLAN.read_text(encoding="utf-8")
    assert "run_streamlit_lan.sh" in text
    assert "removed" in text.lower()
    assert not (_REPO / "scripts/tools/run_streamlit_lan.sh").exists()


def test_launch_plan_documents_streamlit_docker_removal() -> None:
    text = _LAUNCH_PLAN.read_text(encoding="utf-8")
    assert "Dockerfile" in text
    assert "docker-compose.yml" in text
    assert "removed" in text.lower()
    assert not (_REPO / "Dockerfile").exists()
    assert not (_REPO / "docker-compose.yml").exists()
    assert (_REPO / "docker-compose.dashboard-postgres.yml").is_file()


def test_streamlit_python_ui_modules_removed() -> None:
    text = _LAUNCH_PLAN.read_text(encoding="utf-8")
    for name in (
        "business_mart_app.py",
        "streamlit_prioridad_pages.py",
        "streamlit_prioridad_handoffs.py",
        "streamlit_page_status.py",
    ):
        assert name in text
        assert "removed" in text.lower()
    assert not (_REPO / "apps" / "business_mart_app.py").exists()
    assert not (_REPO / "src" / "origenlab_email_pipeline" / "streamlit_prioridad_pages.py").exists()
    assert not (_REPO / "src" / "origenlab_email_pipeline" / "streamlit_prioridad_handoffs.py").exists()
    assert not (_REPO / "src" / "origenlab_email_pipeline" / "streamlit_page_status.py").exists()


def test_active_stack_doc_still_names_dashboard_api_mirror() -> None:
    text = _PLAN.read_text(encoding="utf-8")
    for term in ("apps/dashboard", "apps/api", "Postgres mirror"):
        assert term in text, f"plan doc must still mention {term!r}"
