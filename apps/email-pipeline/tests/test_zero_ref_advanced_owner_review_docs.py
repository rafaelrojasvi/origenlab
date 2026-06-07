"""Guardrails for zero-ref advanced helper owner-review docs (PR #124)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SHORTLIST = _REPO / "docs" / "audits" / "REDUCTION_SHORTLIST_20260607.md"
_SCRIPT_MAP = _REPO / "docs" / "SCRIPT_MAP.md"

_SPANISH_SCRIPT = "export_leads_spanish_csvs.py"
_WEB_SERVER_SCRIPT = "run_contact_hunt_web_server.py"


def test_shortlist_mentions_zero_ref_advanced_scripts() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    assert _SPANISH_SCRIPT in text
    assert _WEB_SERVER_SCRIPT in text


def test_shortlist_documents_owner_review() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8").lower()
    assert "owner review" in text or "needs owner review" in text
    assert "needs_owner_review" in text or "needs owner review" in text


def test_shortlist_export_flag_is_input_path_not_boolean_write() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8").lower()
    assert "--export" in text
    assert "input path" in text or "input file path" in text
    assert "boolean" in text or "do not" in text


def test_shortlist_mentions_future_write_output_flag_names() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8").lower()
    assert "--write-outputs" in text or "write-outputs" in text
    assert "--emit" in text or "emit" in text


def test_shortlist_wrapper_before_delete() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    lower = text.lower()
    assert "legacy_do_not_use" in lower or "wrapper" in lower
    assert "delete" in lower
    assert "not" in lower and ("delete-now" in lower or "immediate deletion" in lower or "not immediate" in lower)


def test_script_map_does_not_classify_helpers_as_active_operator_command() -> None:
    text = _SCRIPT_MAP.read_text(encoding="utf-8")
    for script in (_SPANISH_SCRIPT, _WEB_SERVER_SCRIPT):
        assert script in text
        for line in text.splitlines():
            if script not in line:
                continue
            assert "active_operator_command" not in line, (
                f"{script} must not be classified active_operator_command: {line!r}"
            )


def test_script_map_marks_helpers_parked_or_owner_review() -> None:
    text = _SCRIPT_MAP.read_text(encoding="utf-8").lower()
    assert _SPANISH_SCRIPT in text
    assert _WEB_SERVER_SCRIPT in text
    assert "owner review" in text or "parked" in text
    assert "reduction_shortlist_20260607" in text or "reduction_shortlist" in text
