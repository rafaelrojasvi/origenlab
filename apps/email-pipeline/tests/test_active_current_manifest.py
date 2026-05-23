"""Guardrails: active/current/manifest.json and canonical workspace files."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from origenlab_email_pipeline.active_current_manifest import (
    ALLOWED_CAMPAIGN_MODES,
    load_manifest,
    validate_manifest,
)

REPO = Path(__file__).resolve().parents[1]
ACTIVE_CURRENT = REPO / "reports/out/active/current"
ACTIVE_ROOT = REPO / "reports/out/active"
MANIFEST_PATH = ACTIVE_CURRENT / "manifest.json"
_FIXTURE_ACTIVE_ROOT = REPO / "tests/fixtures/active_current_workspace/active"


@dataclass(frozen=True)
class ActiveWorkspace:
    current: Path
    root: Path
    manifest_path: Path
    source: str


def _resolve_active_workspace() -> ActiveWorkspace:
    if MANIFEST_PATH.is_file():
        return ActiveWorkspace(
            current=ACTIVE_CURRENT,
            root=ACTIVE_ROOT,
            manifest_path=MANIFEST_PATH,
            source="repo",
        )
    fixture_current = _FIXTURE_ACTIVE_ROOT / "current"
    fixture_manifest = fixture_current / "manifest.json"
    assert fixture_manifest.is_file(), f"missing CI fixture manifest: {fixture_manifest}"
    return ActiveWorkspace(
        current=fixture_current,
        root=_FIXTURE_ACTIVE_ROOT,
        manifest_path=fixture_manifest,
        source="fixture",
    )


@pytest.fixture
def active_workspace() -> Iterator[ActiveWorkspace]:
    yield _resolve_active_workspace()


def test_manifest_file_exists(active_workspace: ActiveWorkspace) -> None:
    assert active_workspace.manifest_path.is_file(), (
        f"missing {active_workspace.manifest_path} ({active_workspace.source})"
    )


def test_manifest_validates_against_workspace(active_workspace: ActiveWorkspace) -> None:
    manifest = load_manifest(active_workspace.manifest_path)
    errors = validate_manifest(
        manifest,
        active_current=active_workspace.current,
        active_root=active_workspace.root,
    )
    assert errors == [], "manifest validation errors:\n" + "\n".join(errors)


def test_required_equipment_first_artifacts_exist(active_workspace: ActiveWorkspace) -> None:
    current = active_workspace.current
    assert (current / "equipment_first_operator_queue_20260518.csv").is_file()
    assert (current / "buyer_opportunity_ab_queue_20260518.csv").is_file()


def test_crosscheck_not_canonical(active_workspace: ActiveWorkspace) -> None:
    manifest = load_manifest(active_workspace.manifest_path)
    canonical = set(manifest.get("canonical_files") or [])
    assert "buyer_opportunity_crosscheck_20260518.csv" not in canonical
    stale = {s.get("path") for s in manifest.get("stale_files") or []}
    assert "buyer_opportunity_crosscheck_20260518.csv" in stale


def test_stale_not_in_canonical(active_workspace: ActiveWorkspace) -> None:
    manifest = load_manifest(active_workspace.manifest_path)
    canonical = set(manifest.get("canonical_files") or [])
    for entry in manifest.get("stale_files") or []:
        path = entry.get("path")
        assert path not in canonical, f"stale file {path!r} must not be canonical"


def test_postgres_and_api_parked(active_workspace: ActiveWorkspace) -> None:
    manifest = load_manifest(active_workspace.manifest_path)
    assert manifest.get("postgres_status") == "parked"
    assert manifest.get("api_status") == "parked"


def test_fastlab_warning_in_manifest(active_workspace: ActiveWorkspace) -> None:
    manifest = load_manifest(active_workspace.manifest_path)
    text = " ".join(manifest.get("known_warnings") or []).lower()
    assert "fastlab" in text
    assert "not_contacted" in text or "corrected" in text
    assert "manual_state_only_pending" not in text
    assert "outreach_state contacted" not in text
    notes = manifest.get("operator_notes") or {}
    fastlab = notes.get("fastlab") or {}
    assert fastlab.get("outreach_state") == "not_contacted"
    assert fastlab.get("treat_as_completed_outreach") is False


def test_manifest_json_parseable(active_workspace: ActiveWorkspace) -> None:
    data = json.loads(active_workspace.manifest_path.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1"


def test_manifest_campaign_mode_allowed(active_workspace: ActiveWorkspace) -> None:
    manifest = load_manifest(active_workspace.manifest_path)
    mode = manifest.get("campaign_mode")
    assert mode in ALLOWED_CAMPAIGN_MODES
    assert manifest.get("current_operator_focus")
    errors = validate_manifest(
        manifest,
        active_current=active_workspace.current,
        active_root=active_workspace.root,
    )
    assert not any("campaign_mode" in e for e in errors), errors
