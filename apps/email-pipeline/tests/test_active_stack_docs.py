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
