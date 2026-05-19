"""Guardrails: active/current/manifest.json and canonical workspace files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.active_current_manifest import load_manifest, validate_manifest

REPO = Path(__file__).resolve().parents[1]
ACTIVE_CURRENT = REPO / "reports/out/active/current"
ACTIVE_ROOT = REPO / "reports/out/active"
MANIFEST_PATH = ACTIVE_CURRENT / "manifest.json"


def test_manifest_file_exists() -> None:
    assert MANIFEST_PATH.is_file(), f"missing {MANIFEST_PATH}"


def test_manifest_validates_against_workspace() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    errors = validate_manifest(manifest, active_current=ACTIVE_CURRENT, active_root=ACTIVE_ROOT)
    assert errors == [], "manifest validation errors:\n" + "\n".join(errors)


def test_required_equipment_first_artifacts_exist() -> None:
    assert (ACTIVE_CURRENT / "equipment_first_operator_queue_20260518.csv").is_file()
    assert (ACTIVE_CURRENT / "buyer_opportunity_ab_queue_20260518.csv").is_file()


def test_crosscheck_not_canonical() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    canonical = set(manifest.get("canonical_files") or [])
    assert "buyer_opportunity_crosscheck_20260518.csv" not in canonical
    stale = {s.get("path") for s in manifest.get("stale_files") or []}
    assert "buyer_opportunity_crosscheck_20260518.csv" in stale


def test_stale_not_in_canonical() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    canonical = set(manifest.get("canonical_files") or [])
    for entry in manifest.get("stale_files") or []:
        path = entry.get("path")
        assert path not in canonical, f"stale file {path!r} must not be canonical"


def test_postgres_and_api_parked() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    assert manifest.get("postgres_status") == "parked"
    assert manifest.get("api_status") == "parked"


def test_fastlab_warning_in_manifest() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    text = " ".join(manifest.get("known_warnings") or []).lower()
    assert "fastlab" in text
    assert "pending" in text or "verification" in text
    notes = manifest.get("operator_notes") or {}
    fastlab = notes.get("fastlab") or {}
    assert fastlab.get("status") == "manual_state_only_pending_sent_verification"


def test_manifest_json_parseable() -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "1"
