"""API-3 Phase 3A: non-Dashboard consumers prefer :8001 /mirror routes in docs."""

from __future__ import annotations

from pathlib import Path

from parity_routes import LEGACY_TO_MIRROR_ROUTE_PAIRS

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNBOOK = _REPO_ROOT / "apps" / "email-pipeline" / "docs" / "RUNBOOK.md"
_SYNC_PY = _REPO_ROOT / "apps" / "email-pipeline" / "src" / "origenlab_email_pipeline" / "dashboard_postgres_sync.py"
_ENV_EXAMPLE = _REPO_ROOT / "apps" / "email-pipeline" / ".env.example"
_LEGACY_API_ROOT = _REPO_ROOT / "apps" / "email-pipeline" / "src" / "origenlab_api"
_MIRROR_SMOKE = _REPO_ROOT / "apps" / "dashboard" / "scripts" / "mirror-smoke.mjs"
_DASHBOARD_PKG = _REPO_ROOT / "apps" / "dashboard" / "package.json"
_DASHBOARD_ACTIVE = (
    _REPO_ROOT / "apps" / "dashboard" / "src" / "api" / "operatorClient.ts",
    _REPO_ROOT / "apps" / "dashboard" / "src" / "pages" / "TodayPage.tsx",
)


def test_runbook_prefers_mirror_api_on_8001() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "mirror API :8001 (preferred" in text
    assert "legacy API :8000 (deprecated)" in text
    assert "http://127.0.0.1:8001/mirror/dashboard/summary" in text
    assert "http://127.0.0.1:8000/dashboard/summary" in text
    preferred_idx = text.index("8001/mirror/dashboard/summary")
    legacy_idx = text.index("8000/dashboard/summary")
    assert preferred_idx < legacy_idx


def test_runbook_documents_all_mirror_route_prefixes() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    for _legacy, mirror, _note in LEGACY_TO_MIRROR_ROUTE_PAIRS:
        assert mirror in text, f"RUNBOOK missing mirror path {mirror}"


def test_sync_post_apply_hints_prefer_mirror_curls() -> None:
    text = _SYNC_PY.read_text(encoding="utf-8")
    assert "8001/mirror/dashboard/summary" in text
    assert "8000/dashboard/summary" in text
    assert text.index("8001/mirror") < text.index("8000/dashboard")


def test_env_example_defaults_document_8001_mirror() -> None:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "127.0.0.1:8001" in text
    assert "/mirror/*" in text or "mirror" in text.lower()


def test_mirror_smoke_script_and_npm_command_exist() -> None:
    assert _MIRROR_SMOKE.is_file()
    smoke_text = _MIRROR_SMOKE.read_text(encoding="utf-8")
    assert "/mirror/health/dependencies" in smoke_text
    assert "/mirror/dashboard/summary" in smoke_text
    pkg = _DASHBOARD_PKG.read_text(encoding="utf-8")
    assert '"smoke:mirror"' in pkg
    assert '"smoke:legacy"' in pkg


def test_legacy_api_tree_still_present_phase3() -> None:
    assert (_LEGACY_API_ROOT / "main.py").is_file()


def test_active_dashboard_still_no_mirror_calls_phase3() -> None:
    for path in _DASHBOARD_ACTIVE:
        assert "/mirror/" not in path.read_text(encoding="utf-8")
