"""Lead-account root shims: COMPATIBILITY_WRAPPER contract (docs + file headers).

No production DB, Gmail, or --apply.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Root shim → canonical implementation (scripts/leads/advanced/)
LEAD_ACCOUNT_COMPAT_WRAPPERS: dict[str, str] = {
    "scripts/build_lead_account_rollup.py": "scripts/leads/advanced/build_lead_account_rollup.py",
    "scripts/match_lead_accounts_to_existing_orgs.py": (
        "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py"
    ),
    "scripts/validate_lead_account_rollup.py": "scripts/leads/advanced/validate_lead_account_rollup.py",
    "scripts/audit_lead_org_quality.py": "scripts/leads/advanced/audit_lead_org_quality.py",
}

_OPERATOR_DOCS = (
    REPO / "docs/SCRIPT_MAP.md",
    REPO / "docs/OPERATOR_CHEAT_SHEET.md",
    REPO / "docs/SCRIPT_INVENTORY.md",
)


@pytest.mark.parametrize("wrapper,canonical", list(LEAD_ACCOUNT_COMPAT_WRAPPERS.items()))
def test_wrapper_and_canonical_exist(wrapper: str, canonical: str) -> None:
    assert (REPO / wrapper).is_file(), wrapper
    assert (REPO / canonical).is_file(), canonical


@pytest.mark.parametrize("wrapper", list(LEAD_ACCOUNT_COMPAT_WRAPPERS))
def test_wrapper_docstring_marked_compatibility_only(wrapper: str) -> None:
    text = (REPO / wrapper).read_text(encoding="utf-8")[:4_000].lower()
    assert "compatibility_wrapper" in text or "compatibility_only" in text, wrapper
    assert "leads/advanced" in text, wrapper
    assert "not preferred" in text or "do not add logic" in text, wrapper


def test_script_map_labels_wrappers_not_preferred() -> None:
    body = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8")
    section_start = body.find("## Lead-account scripts: canonical vs root wrappers")
    assert section_start >= 0, "SCRIPT_MAP missing lead-account wrapper section"
    section = body[section_start : section_start + 6_000]
    assert "COMPATIBILITY_WRAPPER" in section
    assert "COMPATIBILITY_ONLY" in section
    assert "not preferred" in section.lower()
    for wrapper, canonical in LEAD_ACCOUNT_COMPAT_WRAPPERS.items():
        assert wrapper.replace("scripts/", "") in section or wrapper in section, wrapper
        assert canonical in section, canonical


def test_operator_docs_prefer_advanced_paths_note() -> None:
    needle = "scripts/leads/advanced"
    for path in _OPERATOR_DOCS:
        body = path.read_text(encoding="utf-8")
        assert "COMPATIBILITY" in body, path.name
        assert needle in body, path.name
        assert "compatibility only" in body.lower() or "COMPATIBILITY_ONLY" in body, path.name


def test_help_entrypoints_do_not_list_root_wrappers() -> None:
    src = (REPO / "tests/test_operator_entrypoint_contracts.py").read_text(encoding="utf-8")
    start = src.index("_HELP_ENTRYPOINTS")
    end = src.index("_BREAK_GLASS_PATHS", start)
    help_block = src[start:end]
    roots = set(LEAD_ACCOUNT_COMPAT_WRAPPERS)
    overlap = {r for r in roots if f'"{r}"' in help_block}
    assert not overlap, f"root wrappers must not be daily --help entrypoints: {overlap}"


def test_critical_paths_include_both_wrapper_and_canonical() -> None:
    """Wrappers stay on disk; canonical paths are the implementation contract."""
    src = (REPO / "tests/test_critical_script_paths.py").read_text(encoding="utf-8")
    for wrapper, canonical in LEAD_ACCOUNT_COMPAT_WRAPPERS.items():
        assert wrapper in src, wrapper
        assert canonical in src, canonical
