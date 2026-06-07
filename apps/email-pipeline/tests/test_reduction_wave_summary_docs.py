"""Guardrails for docs/audits/REDUCTION_WAVE_20260607_SUMMARY.md (PR #127)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SUMMARY = _REPO / "docs" / "audits" / "REDUCTION_WAVE_20260607_SUMMARY.md"
_SHORTLIST = _REPO / "docs" / "audits" / "REDUCTION_SHORTLIST_20260607.md"

_COMPLETED_PRS = ("#118", "#119", "#122", "#123", "#125", "#126")
_WRITE_FLAGS = ("--apply", "--build-batch", "--write-outputs", "--lan")
_BOUNDARIES = (
    "gmail ingest",
    "send",
    "purge",
    "ndr",
    "postgres",
    "alembic",
    "outbound",
    "daily-core",
)


def test_reduction_wave_summary_doc_exists() -> None:
    assert _SUMMARY.is_file(), f"missing wave summary: {_SUMMARY}"


def test_summary_mentions_completed_prs() -> None:
    text = _SUMMARY.read_text(encoding="utf-8")
    for pr in _COMPLETED_PRS:
        assert pr in text, f"summary must mention completed PR {pr}"


def test_summary_mentions_write_and_exposure_flags() -> None:
    text = _SUMMARY.read_text(encoding="utf-8")
    for flag in _WRITE_FLAGS:
        assert flag in text, f"summary must mention flag {flag!r}"


def test_summary_preserves_no_touch_boundaries() -> None:
    text = _SUMMARY.read_text(encoding="utf-8").lower()
    for boundary in _BOUNDARIES:
        assert boundary in text, f"summary must note boundary not changed: {boundary!r}"


def test_shortlist_links_to_wave_summary() -> None:
    text = _SHORTLIST.read_text(encoding="utf-8")
    assert "REDUCTION_WAVE_20260607_SUMMARY.md" in text
    lower = text.lower()
    assert "closed" in lower or "closing note" in lower or "wave closed" in lower


def test_summary_closes_wave_and_no_reopen_without_regression() -> None:
    text = _SUMMARY.read_text(encoding="utf-8").lower()
    assert "stop this reduction wave" in text or "wave closed" in text or "closing note" in text
    assert "do not reopen" in text or "do not re-open" in text
    assert "regression" in text
