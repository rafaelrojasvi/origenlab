"""Phase 2 removal evidence report and deprecation documentation locks."""

from __future__ import annotations

from pathlib import Path

import pytest

from removal_evidence import (
    DEPRECATED_REMOVAL_TARGETS,
    REFACTOR_PHASE3_TARGETS,
    REMOVED_PHASE5A_TARGETS,
    REMOVED_PHASE5B_TARGETS,
    REMOVED_PHASE5C_TARGETS,
    REMOVED_PHASE5D_TARGETS,
    REMOVED_PHASE5K_TARGETS,
    build_removal_evidence_markdown,
    reference_counts,
    write_removal_evidence_report,
)

REPO = Path(__file__).resolve().parents[1]


def test_generate_removal_evidence_report() -> None:
    out = write_removal_evidence_report()
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "Phase 2 — script removal evidence" in body
    for row in DEPRECATED_REMOVAL_TARGETS:
        assert row["path"] in body
    for row in REMOVED_PHASE5A_TARGETS:
        assert row["path"] in body
        assert "Removed in Phase 5A" in body
    for row in REMOVED_PHASE5B_TARGETS:
        assert row["path"] in body
        assert "Removed in Phase 5B" in body
    for row in REMOVED_PHASE5C_TARGETS:
        assert row["path"] in body
        assert "Removed in Phase 5C" in body
    for row in REMOVED_PHASE5D_TARGETS:
        assert row["path"] in body
        assert "Removed in Phase 5D" in body
    for row in REMOVED_PHASE5K_TARGETS:
        assert row["path"] in body
        assert "Removed in Phase 5K" in body


def test_deprecated_targets_listed_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    for row in DEPRECATED_REMOVAL_TARGETS:
        assert Path(row["path"]).name in smap or row["path"] in smap, row["path"]


def test_phase5a_removed_shells_documented_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    assert "POST_SEND_SAFE_LOOP.md" in smap
    for row in REMOVED_PHASE5A_TARGETS:
        assert Path(row["path"]).name in smap or "Phase 5A" in smap, row["path"]
        assert not (REPO / row["path"]).is_file(), row["path"]


def test_phase5b_removed_wrappers_documented_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    assert "scripts/leads/advanced" in smap
    for row in REMOVED_PHASE5B_TARGETS:
        assert Path(row["path"]).name in smap or "Phase 5B" in smap, row["path"]
        assert not (REPO / row["path"]).is_file(), row["path"]


def test_phase5c_removed_buyer_queue_documented_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    assert "build_equipment_first_opportunity_queue.py" in smap
    assert "build_equipment_first_operator_queue.py" in smap
    for row in REMOVED_PHASE5C_TARGETS:
        assert Path(row["path"]).name in smap or "Phase 5C" in smap, row["path"]
        assert not (REPO / row["path"]).is_file(), row["path"]


def test_phase5d_removed_archive_wrapper_documented_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    assert "build_archive_send_batch.py" in smap
    assert "--audit-only" in smap or "audit-only" in smap
    for row in REMOVED_PHASE5D_TARGETS:
        assert Path(row["path"]).name in smap or "Phase 5D" in smap, row["path"]
        assert not (REPO / row["path"]).is_file(), row["path"]


def test_phase5k_removed_manual_outreach_oneoffs_documented_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    assert "build_post_send_digest.py" in smap
    assert "POST_SEND_SAFE_LOOP.md" in smap
    for row in REMOVED_PHASE5K_TARGETS:
        assert Path(row["path"]).name in smap or "Phase 5K" in smap, row["path"]
        assert not (REPO / row["path"]).is_file(), row["path"]


@pytest.mark.parametrize("rel", [r["path"] for r in REMOVED_PHASE5A_TARGETS])
def test_phase5a_removed_shells_not_on_disk(rel: str) -> None:
    assert not (REPO / rel).is_file(), f"Phase 5A removed: {rel}"


@pytest.mark.parametrize("rel", [r["path"] for r in REMOVED_PHASE5B_TARGETS])
def test_phase5b_removed_wrappers_not_on_disk(rel: str) -> None:
    assert not (REPO / rel).is_file(), f"Phase 5B removed: {rel}"


@pytest.mark.parametrize("rel", [r["path"] for r in REMOVED_PHASE5C_TARGETS])
def test_phase5c_removed_buyer_queue_not_on_disk(rel: str) -> None:
    assert not (REPO / rel).is_file(), f"Phase 5C removed: {rel}"


@pytest.mark.parametrize("rel", [r["path"] for r in REMOVED_PHASE5D_TARGETS])
def test_phase5d_removed_archive_wrapper_not_on_disk(rel: str) -> None:
    assert not (REPO / rel).is_file(), f"Phase 5D removed: {rel}"


@pytest.mark.parametrize("rel", [r["path"] for r in REMOVED_PHASE5K_TARGETS])
def test_phase5k_removed_manual_outreach_oneoffs_not_on_disk(rel: str) -> None:
    assert not (REPO / rel).is_file(), f"Phase 5K removed: {rel}"


def test_refactor_phase3_targets_documented() -> None:
    audit = (REPO / "docs/audits/CODEBASE_SIMPLIFICATION_AUDIT_20260602.md").read_text(encoding="utf-8")
    for row in REFACTOR_PHASE3_TARGETS:
        assert row["path"] in audit


@pytest.mark.parametrize("rel", [r["path"] for r in DEPRECATED_REMOVAL_TARGETS])
def test_deprecated_script_file_still_exists(rel: str) -> None:
    assert (REPO / rel).is_file(), f"deprecated target must remain on disk: {rel}"


def test_evidence_markdown_has_table_rows() -> None:
    md = build_removal_evidence_markdown()
    assert "| `scripts/tools/flag_reported_non_delivery_from_contacto.py` |" in md
    assert "Removed in Phase 5C" in md
    assert "Removed in Phase 5D" in md
    assert "Removed in Phase 5K" in md


def test_reference_counts_returns_non_negative() -> None:
    rc = reference_counts("scripts/tools/flag_reported_non_delivery_from_contacto.py")
    assert rc.docs >= 0
    assert rc.tests >= 0
    assert rc.in_script_map


def test_deprecated_python_scripts_use_phase4_stderr_helpers() -> None:
    legacy_ndr = (REPO / "scripts/tools/flag_reported_non_delivery_from_contacto.py").read_text(
        encoding="utf-8",
    )
    assert "print_script_deprecation_warning" in legacy_ndr
