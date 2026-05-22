"""API-3 Phase 2: mirror parity checklist enforcement (docs/tests only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from origenlab_api.main import create_app

from parity_routes import (
    LEGACY_HEALTH_NO_MIRROR_ALIAS,
    LEGACY_TO_MIRROR_ROUTE_PAIRS,
    OPERATOR_TODAY_PATHS,
    REQUIRED_MIRROR_OPENAPI_PATHS,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LEGACY_API_ROOT = _REPO_ROOT / "apps" / "email-pipeline" / "src" / "origenlab_api"
_DASHBOARD_ACTIVE_SOURCES = (
    _REPO_ROOT / "apps" / "dashboard" / "src" / "api" / "operatorClient.ts",
    _REPO_ROOT / "apps" / "dashboard" / "src" / "pages" / "TodayPage.tsx",
    _REPO_ROOT / "apps" / "dashboard" / "src" / "App.tsx",
    _REPO_ROOT / "apps" / "dashboard" / "vite.config.ts",
)


def test_legacy_origenlab_api_tree_still_exists() -> None:
    assert _LEGACY_API_ROOT.is_dir(), f"missing legacy tree: {_LEGACY_API_ROOT}"
    assert (_LEGACY_API_ROOT / "main.py").is_file()
    assert (_LEGACY_API_ROOT / "routers").is_dir()


def test_documented_mirror_routes_exist_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    missing = [p for p in REQUIRED_MIRROR_OPENAPI_PATHS if p not in paths]
    assert missing == [], f"mirror paths missing from OpenAPI: {missing}"


def test_documented_mirror_routes_are_get_only_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    unsafe: list[str] = []
    for mirror_path in REQUIRED_MIRROR_OPENAPI_PATHS:
        ops = paths.get(mirror_path) or {}
        for method in ops:
            if method.lower() not in ("get", "parameters"):
                unsafe.append(f"{mirror_path} {method.upper()}")
    assert unsafe == [], f"non-GET mirror OpenAPI operations: {unsafe}"


def test_legacy_health_has_no_mirror_alias() -> None:
    paths = create_app().openapi()["paths"]
    assert LEGACY_HEALTH_NO_MIRROR_ALIAS in paths
    assert "/mirror/health" not in paths
    assert f"/mirror{LEGACY_HEALTH_NO_MIRROR_ALIAS}" not in paths


def test_operator_contact_detail_distinct_from_mirror_contacts_list() -> None:
    paths = create_app().openapi()["paths"]
    assert "/mirror/contacts" in paths
    assert "/contacts/{email}" in paths
    assert "/mirror/contacts/{email}" not in paths
    assert "/mirror/contacts/{event_id}" not in paths


def test_operator_today_routes_remain_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    missing = [p for p in OPERATOR_TODAY_PATHS if p not in paths]
    assert missing == [], f"operator Today paths missing: {missing}"


def test_active_dashboard_sources_do_not_call_mirror_routes() -> None:
    hits: list[str] = []
    for path in _DASHBOARD_ACTIVE_SOURCES:
        text = path.read_text(encoding="utf-8")
        if "/mirror/" in text or '"/mirror"' in text:
            hits.append(str(path.relative_to(_REPO_ROOT)))
    assert hits == [], f"active dashboard must not reference /mirror/*: {hits}"


def test_parity_route_pair_count_matches_phase2_checklist() -> None:
    """Lock checklist size so a new legacy route forces doc + test updates."""
    assert len(LEGACY_TO_MIRROR_ROUTE_PAIRS) == 13


def test_mirror_parity_checklist_doc_exists() -> None:
    doc = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "API-3_PHASE2_PARITY_CHECKLIST.md"
    )
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for legacy, mirror, _note in LEGACY_TO_MIRROR_ROUTE_PAIRS:
        assert legacy in text, f"doc missing legacy path {legacy}"
        assert mirror in text, f"doc missing mirror path {mirror}"
