"""Guardrails for canonical daily core operator contract (docs-only)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_DAILY_CORE = _REPO / "docs" / "pipeline" / "DAILY_CORE.md"
_OPERATOR_SURFACE = _REPO / "docs" / "OPERATOR_COMMAND_SURFACE.md"
_RUNBOOK = _REPO / "docs" / "RUNBOOK.md"

_CANONICAL_CMD = "uv run origenlab daily-core --apply"
_PLAN_CMD = "uv run origenlab daily-core"
_EQUIVALENT_APPLY = "uv run origenlab refresh-dashboard --apply --no-mirror"
_EQUIVALENT_PLAN = "uv run origenlab refresh-dashboard"
_CORE_STEPS = (
    "gmail-ingest",
    "build-mart",
    "build-commercial-intel",
    "refresh-safety",
    "ndr-review",
    "post-send-digest",
    "status",
)


def test_daily_core_md_exists() -> None:
    assert _DAILY_CORE.is_file(), f"missing canonical doc: {_DAILY_CORE}"


def test_daily_core_documents_canonical_apply_no_mirror_command() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    assert _CANONICAL_CMD in text
    assert _EQUIVALENT_APPLY in text


def test_daily_core_documents_plan_only_command() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    assert _PLAN_CMD in text
    assert _EQUIVALENT_PLAN in text or "refresh-dashboard" in text
    assert "plan-only" in text.lower() or "plan only" in text.lower()


def test_daily_core_lists_all_seven_steps() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    for step in _CORE_STEPS:
        assert step in text, f"DAILY_CORE.md must mention step {step!r}"


def test_daily_core_sqlite_and_gmail_sent_operational_truth() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "sqlite" in lower
    assert "gmail sent" in lower or "sent history" in lower or "sent folder" in lower
    assert "operational truth" in lower


def test_daily_core_postgres_mirror_read_only_not_send_approval() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "postgres" in lower
    assert "read-only" in lower or "read only" in lower
    assert "not send approval" in lower or "does not approve" in lower


def test_daily_core_safety_boundaries() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "does not send" in lower
    assert "does not purge" in lower
    assert "does not apply ndr" in lower or "does not apply ndr suppressions" in lower
    assert "does not run alembic" in lower


def test_daily_core_optional_mirror_separate() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    assert "mirror-dashboard" in text
    assert "separate" in text.lower() or "outside" in text.lower() or "optional" in text.lower()


def test_operator_command_surface_links_daily_core() -> None:
    text = _OPERATOR_SURFACE.read_text(encoding="utf-8")
    assert "pipeline/DAILY_CORE.md" in text or "DAILY_CORE.md" in text


def test_runbook_links_daily_core() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "pipeline/DAILY_CORE.md" in text or "DAILY_CORE.md" in text


def test_daily_core_documents_run_manifest() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    assert "daily_core_run_manifest.json" in text
    assert "manifest.json" in text
    lower = text.lower()
    assert "not send approval" in lower or "visibility" in lower
    assert "separate" in lower
