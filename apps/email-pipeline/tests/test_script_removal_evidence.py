"""Phase 2 removal evidence report and deprecation documentation locks."""

from __future__ import annotations

from pathlib import Path

import pytest

from removal_evidence import (
    DEPRECATED_REMOVAL_TARGETS,
    REFACTOR_PHASE3_TARGETS,
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


def test_deprecated_targets_listed_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    for row in DEPRECATED_REMOVAL_TARGETS:
        assert Path(row["path"]).name in smap or row["path"] in smap, row["path"]


def test_dated_ops_shells_marked_deprecated_in_script_map() -> None:
    smap = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    assert "run_post_send_2026_06_01_refresh.sh" in smap
    assert "DEPRECATED" in smap
    assert "run_manual_outreach_2026_06_01_post_send_refresh.sh" in smap


def test_refactor_phase3_targets_documented() -> None:
    audit = (REPO / "docs/audits/CODEBASE_SIMPLIFICATION_AUDIT_20260602.md").read_text(encoding="utf-8")
    for row in REFACTOR_PHASE3_TARGETS:
        assert row["path"] in audit


@pytest.mark.parametrize("rel", [r["path"] for r in DEPRECATED_REMOVAL_TARGETS])
def test_deprecated_script_file_still_exists(rel: str) -> None:
    assert (REPO / rel).is_file(), f"Phase 2 must not delete: {rel}"


def test_evidence_markdown_has_table_rows() -> None:
    md = build_removal_evidence_markdown()
    assert "| `scripts/qa/build_buyer_opportunity_queue.py` |" in md


def test_reference_counts_returns_non_negative() -> None:
    rc = reference_counts("scripts/qa/build_buyer_opportunity_queue.py")
    assert rc.docs >= 0
    assert rc.tests >= 0
    assert rc.in_script_map


def test_deprecated_python_scripts_use_phase4_stderr_helpers() -> None:
    buyer = (REPO / "scripts/qa/build_buyer_opportunity_queue.py").read_text(encoding="utf-8")
    assert "print_script_deprecation_warning" in buyer
    legacy_ndr = (REPO / "scripts/tools/flag_reported_non_delivery_from_contacto.py").read_text(
        encoding="utf-8",
    )
    assert "print_script_deprecation_warning" in legacy_ndr
    archive = (
        REPO / "scripts/leads/advanced/export_archive_outreach_candidates.py"
    ).read_text(encoding="utf-8")
    assert "print_script_deprecation_warning" in archive
    wrapper = (REPO / "scripts/build_lead_account_rollup.py").read_text(encoding="utf-8")
    assert "print_wrapper_deprecation_warning" in wrapper or "_script_warnings" in wrapper
