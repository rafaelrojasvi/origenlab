"""Lead-account canonical scripts: docs contract and critical paths (Phase 5B).

Root ``scripts/*.py`` compatibility wrappers were removed in Phase 5B.
No production DB, Gmail, or --apply.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

LEAD_ACCOUNT_CANONICAL_SCRIPTS: tuple[str, ...] = (
    "scripts/leads/advanced/build_lead_account_rollup.py",
    "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py",
    "scripts/leads/advanced/validate_lead_account_rollup.py",
    "scripts/leads/advanced/audit_lead_org_quality.py",
)

REMOVED_PHASE5B_WRAPPERS: tuple[str, ...] = (
    "scripts/build_lead_account_rollup.py",
    "scripts/match_lead_accounts_to_existing_orgs.py",
    "scripts/validate_lead_account_rollup.py",
    "scripts/audit_lead_org_quality.py",
)

_OPERATOR_DOCS = (
    REPO / "docs/SCRIPT_MAP.md",
    REPO / "docs/OPERATOR_CHEAT_SHEET.md",
    REPO / "docs/SCRIPT_INVENTORY.md",
)


@pytest.mark.parametrize("canonical", LEAD_ACCOUNT_CANONICAL_SCRIPTS)
def test_canonical_lead_account_script_exists(canonical: str) -> None:
    assert (REPO / canonical).is_file(), canonical


@pytest.mark.parametrize("wrapper", REMOVED_PHASE5B_WRAPPERS)
def test_phase5b_root_wrappers_removed(wrapper: str) -> None:
    assert not (REPO / wrapper).is_file(), f"Phase 5B removed: {wrapper}"


def test_script_map_documents_canonical_lead_account_paths() -> None:
    body = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    section_start = body.find("## Lead-account scripts")
    assert section_start >= 0, "SCRIPT_MAP missing lead-account section"
    section = body[section_start : section_start + 6_000]
    assert "scripts/leads/advanced" in section
    assert "Phase 5B" in section or "Removed Phase 5B" in section
    for canonical in LEAD_ACCOUNT_CANONICAL_SCRIPTS:
        assert canonical in section or Path(canonical).name in section, canonical


def test_operator_docs_prefer_advanced_paths() -> None:
    needle = "scripts/leads/advanced"
    for path in _OPERATOR_DOCS:
        body = path.read_text(encoding="utf-8")
        assert needle in body, path.name


def test_help_entrypoints_do_not_list_removed_root_wrappers() -> None:
    src = (REPO / "tests/test_operator_entrypoint_contracts.py").read_text(encoding="utf-8")
    start = src.index("_HELP_ENTRYPOINTS")
    end = src.index("_BREAK_GLASS_PATHS", start)
    help_block = src[start:end]
    overlap = {w for w in REMOVED_PHASE5B_WRAPPERS if f'"{w}"' in help_block}
    assert not overlap, f"removed wrappers must not be daily --help entrypoints: {overlap}"


def test_critical_paths_include_canonical_only() -> None:
    src = (REPO / "tests/test_critical_script_paths.py").read_text(encoding="utf-8")
    for canonical in LEAD_ACCOUNT_CANONICAL_SCRIPTS:
        assert canonical in src, canonical
    for wrapper in REMOVED_PHASE5B_WRAPPERS:
        assert wrapper not in src, wrapper
