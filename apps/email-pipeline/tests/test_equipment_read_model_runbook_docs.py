"""Guardrails for equipment read-model operator runbook (docs-only)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_RUNBOOK = _REPO / "docs" / "runbooks" / "EQUIPMENT_READ_MODEL_RUNBOOK.md"
_BOUNDARY = _REPO / "docs" / "architecture" / "EQUIPMENT_READ_MODEL_BOUNDARY.md"
_API_README = _REPO.parents[0] / "api" / "README.md"


def test_equipment_read_model_runbook_exists() -> None:
    assert _RUNBOOK.is_file(), f"missing canonical doc: {_RUNBOOK}"


def test_equipment_read_model_runbook_mentions_current_view() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "api.v_equipment_opportunity_current" in text


def test_equipment_read_model_runbook_mentions_remote_audit_script() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "remote_response_audit.py" in text


def test_equipment_read_model_runbook_mentions_source_path_redaction() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "source_path_info.redacted" in text


def test_equipment_read_model_boundary_links_runbook() -> None:
    text = _BOUNDARY.read_text(encoding="utf-8")
    assert "EQUIPMENT_READ_MODEL_RUNBOOK.md" in text


def test_api_readme_links_equipment_read_model_runbook() -> None:
    text = _API_README.read_text(encoding="utf-8")
    assert "EQUIPMENT_READ_MODEL_RUNBOOK.md" in text
