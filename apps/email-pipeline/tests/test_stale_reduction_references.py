"""Docs guard: removed reduction targets are not presented as live operator paths."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS_README = _REPO / "scripts" / "README.md"

# Markdown links that point at leads/<script>.py without advanced/ (not backtick warnings).
_BAD_LEAD_LINK = re.compile(
    r"\]\((?:\.\./)*(?:scripts/)?leads/(?!advanced/)"
    r"(?:build_lead_account_rollup|match_lead_accounts_to_existing_orgs|"
    r"validate_lead_account_rollup|audit_lead_org_quality)\.py\)"
)

_REMOVED_BUYER_QUEUE = _REPO / "scripts" / "qa" / "build_buyer_opportunity_queue.py"
_INVOKE_BUYER_QUEUE = re.compile(
    r"(?:uv run|python scripts/qa/)build_buyer_opportunity_queue",
    re.IGNORECASE,
)

_ACTIVE_OPERATOR_DOCS = (
    _SCRIPTS_README,
    _REPO / "docs" / "OPERATOR_COMMAND_SURFACE.md",
    _REPO / "docs" / "RUNBOOK.md",
    _REPO / "AGENTS.md",
)


def test_scripts_readme_does_not_link_nonexistent_lead_account_paths() -> None:
    text = _SCRIPTS_README.read_text(encoding="utf-8")
    match = _BAD_LEAD_LINK.search(text)
    assert match is None, f"scripts/README.md must not link missing lead-account path: {match.group(0) if match else ''}"
    assert "scripts/leads/advanced/" in text


def test_build_buyer_opportunity_queue_removed_not_live() -> None:
    assert not _REMOVED_BUYER_QUEUE.is_file()
    for path in _ACTIVE_OPERATOR_DOCS:
        body = path.read_text(encoding="utf-8")
        assert _INVOKE_BUYER_QUEUE.search(body) is None, path.name
        if "build_buyer_opportunity_queue" in body:
            lower = body.lower()
            assert "removed" in lower or "phase 5c" in lower, path.name
