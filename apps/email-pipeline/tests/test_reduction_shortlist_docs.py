"""Guardrails for docs/audits/REDUCTION_SHORTLIST_20260607.md."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SHORTLIST = _REPO / "docs" / "audits" / "REDUCTION_SHORTLIST_20260607.md"

_NO_TOUCH_SNIPPETS = (
    "05_workspace_gmail_imap_to_sqlite.py",
    "export_do_not_repeat_master.py",
    "refresh_outbound_safety_memory.py",
    "flag_ndr_bounces_from_contacto.py",
    "candidate_export_gate",
    "outbound_core",
    "outreach_contact_state",
    "csv_contracts",
)

_ACTION_TYPES = (
    "apply_gate",
    "audit_only_default",
    "lab_boundary",
    "delete_later_after_wrapper",
)


def test_reduction_shortlist_doc_exists() -> None:
    assert _SHORTLIST.is_file(), f"missing shortlist audit: {_SHORTLIST}"


def test_reduction_shortlist_mentions_no_touch_paths() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    for snippet in _NO_TOUCH_SNIPPETS:
        assert snippet in text, f"shortlist must list no-touch path: {snippet!r}"


def test_reduction_shortlist_mentions_recent_reduction_prs() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    assert "#118" in text
    assert "prepare_active_workspace" in text
    assert "#119" in text
    assert "build_archive_send_batch" in text


def test_reduction_shortlist_does_not_target_removed_buyer_queue() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    assert "build_buyer_opportunity_queue.py" in text
    lower = text.lower()
    assert "removed" in lower or "phase 5c" in lower or "not a live target" in lower


def test_reduction_shortlist_includes_candidate_action_types() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    for action in _ACTION_TYPES:
        assert action in text, f"shortlist must document action type: {action!r}"


def test_reduction_shortlist_planners_not_deletion_authority() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8").lower()
    assert "not deletion authority" in text or "planners are not deletion authority" in text
