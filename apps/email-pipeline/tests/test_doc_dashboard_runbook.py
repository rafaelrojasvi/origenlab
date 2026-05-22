"""Static checks: dashboard Gmail→React operator docs stay complete."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "docs" / "RUNBOOK.md"
CHEAT = REPO / "docs" / "OPERATOR_CHEAT_SHEET.md"
DASHBOARD_README = REPO.parent / "dashboard" / "README.md"

RUNBOOK_MARKERS = (
    "m-eprun-dashboard-optional",
    "m-eprun-daily-outbound",
    "Daily operator truth",
    "dashboard_stack_simplification_design_20260519.md",
    "m-eprun-dashboard-gmail-to-react",
    "Dashboard refresh: from Gmail to React",
    "canonical-dashboard-refresh-chain",
    "Gmail contacto@origenlab.cl",
    "uv sync --group gmail",
    "sync_dashboard_postgres_mirror.py",
    "SELECT COUNT(*), MAX(date_iso) FROM emails WHERE source_file LIKE 'gmail:contacto@origenlab.cl/%'",
    "set -eo pipefail",
    "RPROMPT: parameter not set",
    "curl -sS http://127.0.0.1:8001/mirror/meta/dashboard-sync",
    "curl -sS http://127.0.0.1:8001/mirror/classification/summary",
    "API-3 Phase 6",
    "8001/mirror",
    "Failed to fetch",
    "scope=archive",
    "never ingests Gmail",
)

CHEAT_MARKERS = (
    "m-opsheet-dashboard-gmail-to-react",
    "Commercial React dashboard",
    "m-eprun-dashboard-optional",
    "canonical-dashboard-refresh-chain",
    "dashboard_stack_simplification_design_20260519.md",
    "refresh_operational_dashboard_stack.py",
    "EXPERIMENTAL_PARKED.md",
)

DASHBOARD_README_MARKERS = (
    "m-eprun-dashboard-gmail-to-react",
    "sync_dashboard_postgres_mirror.py",
    "/mirror/meta/dashboard-sync",
    "/mirror/classification/summary",
    "Failed to fetch",
)


def test_runbook_dashboard_section_present() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for marker in RUNBOOK_MARKERS:
        assert marker in text, f"RUNBOOK missing: {marker!r}"


def test_cheat_sheet_dashboard_section_present() -> None:
    text = CHEAT.read_text(encoding="utf-8")
    for marker in CHEAT_MARKERS:
        assert marker in text, f"OPERATOR_CHEAT_SHEET missing: {marker!r}"


def test_dashboard_readme_links_runbook() -> None:
    text = DASHBOARD_README.read_text(encoding="utf-8")
    for marker in DASHBOARD_README_MARKERS:
        assert marker in text, f"apps/dashboard/README missing: {marker!r}"
