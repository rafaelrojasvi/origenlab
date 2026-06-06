"""Operator status endpoint tests (read-only, no Postgres/Gmail)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import Settings

OPERATOR_STATUS_KEYS = frozenset(
    {
        "verdict",
        "sqlite_path",
        "campaign_mode",
        "operator_focus",
        "outbound_readiness",
        "warnings",
        "daily_core_run",
    }
)

DAILY_CORE_MANIFEST_NAME = "daily_core_run_manifest.json"


def _valid_daily_core_manifest_payload() -> dict:
    return {
        "schema_version": 1,
        "workflow": "daily-core",
        "generated_at_utc": "2026-06-05T12:00:00+00:00",
        "command": "uv run origenlab daily-core --apply",
        "equivalent_command": "uv run origenlab refresh-dashboard --apply --no-mirror",
        "operational_truth": "SQLite + Gmail Sent history inside SQLite",
        "postgres_mirror": "not included",
        "send_approval": False,
        "safety": {"runs_postgres_mirror": False},
        "steps": [
            {"label": "gmail-ingest", "returncode": 0},
            {"label": "build-mart", "returncode": 0},
            {"label": "build-commercial-intel", "returncode": 0},
            {"label": "refresh-safety", "returncode": 0},
            {"label": "ndr-review", "returncode": 0},
            {"label": "post-send-digest", "returncode": 0},
            {"label": "status", "returncode": 0},
        ],
        "status": "success",
        "returncode": 0,
    }


def _client_with_settings(
    tmp_path: Path,
    db: Path | None,
    manifest: dict | None,
    *,
    daily_core_manifest: dict | str | None = None,
) -> TestClient:
    active = tmp_path / "current"
    active.mkdir(parents=True)
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (active / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if daily_core_manifest is not None:
        content = (
            daily_core_manifest
            if isinstance(daily_core_manifest, str)
            else json.dumps(daily_core_manifest)
        )
        (active / DAILY_CORE_MANIFEST_NAME).write_text(content, encoding="utf-8")
    settings = Settings(
        sqlite_path=db,
        active_current=active,
    )
    app = create_app()
    app.dependency_overrides.clear()

    from origenlab_api.settings import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _minimal_manifest() -> dict:
    return {
        "known_warnings": [],
        "canonical_files": [],
        "campaign_mode": "equipment_first",
        "current_operator_focus": "focus",
        "operator_notes": {"fastlab": {"outreach_state": "not_contacted"}},
    }


def _minimal_db(tmp_path: Path) -> Path:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, source_file TEXT, folder TEXT)"
    )
    conn.commit()
    conn.close()
    return db


def test_operator_status_response_stable_keys(tmp_path: Path) -> None:
    """Lock API-0 JSON shape for operator status."""
    db = _minimal_db(tmp_path)
    client = _client_with_settings(tmp_path, db, _minimal_manifest())
    data = client.get("/operator/status").json()
    assert set(data.keys()) == OPERATOR_STATUS_KEYS
    assert isinstance(data["warnings"], list)
    assert isinstance(data["outbound_readiness"], str)
    assert isinstance(data["daily_core_run"], dict)


def test_operator_status_read_only_minimal_sqlite(tmp_path: Path) -> None:
    db = _minimal_db(tmp_path)
    manifest = {
        "known_warnings": ["test warning"],
        "canonical_files": [],
        "campaign_mode": "equipment_first",
        "current_operator_focus": "test focus",
        "operator_notes": {"fastlab": {"outreach_state": "not_contacted"}},
    }
    client = _client_with_settings(tmp_path, db, manifest)
    r = client.get("/operator/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["verdict"] in ("READY", "CAUTION", "BLOCKED")
    assert data["sqlite_path"] == str(db.resolve())
    assert data["campaign_mode"] == "equipment_first"
    assert data["operator_focus"] == "test focus"
    assert isinstance(data["outbound_readiness"], str)
    assert "test warning" in data["warnings"]
    assert set(data.keys()) == OPERATOR_STATUS_KEYS


def test_operator_status_missing_daily_core_manifest_exists_false(tmp_path: Path) -> None:
    db = _minimal_db(tmp_path)
    client = _client_with_settings(tmp_path, db, _minimal_manifest())
    data = client.get("/operator/status").json()
    dcr = data["daily_core_run"]
    assert dcr["exists"] is False
    assert dcr["path"].endswith(DAILY_CORE_MANIFEST_NAME)


def test_operator_status_valid_daily_core_manifest_summary(tmp_path: Path) -> None:
    db = _minimal_db(tmp_path)
    client = _client_with_settings(
        tmp_path,
        db,
        _minimal_manifest(),
        daily_core_manifest=_valid_daily_core_manifest_payload(),
    )
    data = client.get("/operator/status").json()
    dcr = data["daily_core_run"]
    assert dcr["exists"] is True
    assert dcr["loaded"] is True
    assert dcr["workflow"] == "daily-core"
    assert dcr["status"] == "success"
    assert dcr["returncode"] == 0
    assert dcr["step_count"] == 7
    assert dcr["send_approval"] is False
    assert dcr["postgres_mirror"] == "not included"


def test_operator_status_malformed_daily_core_manifest_parse_error_warning(tmp_path: Path) -> None:
    db = _minimal_db(tmp_path)
    client = _client_with_settings(
        tmp_path,
        db,
        _minimal_manifest(),
        daily_core_manifest="{not-json",
    )
    r = client.get("/operator/status")
    assert r.status_code == 200, r.text
    data = r.json()
    dcr = data["daily_core_run"]
    assert dcr["exists"] is True
    assert dcr["loaded"] is False
    assert dcr["parse_error"] is True
    assert any("daily_core_run_manifest.json parse error" in w for w in data["warnings"])


def test_operator_status_missing_sqlite_graceful(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite"
    manifest = {
        "known_warnings": [],
        "canonical_files": [],
        "campaign_mode": "equipment_first",
        "current_operator_focus": "x",
    }
    client = _client_with_settings(tmp_path, missing, manifest)
    r = client.get("/operator/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["verdict"] == "BLOCKED"
    assert data["sqlite_path"] == str(missing.resolve())
    assert data["outbound_readiness"] == "not_ready"
    assert data["daily_core_run"]["exists"] is False


def test_operator_status_no_postgres_env_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)

    db = _minimal_db(tmp_path)
    manifest = {
        "known_warnings": [],
        "canonical_files": [],
        "campaign_mode": "none",
        "current_operator_focus": "ok",
    }
    client = _client_with_settings(tmp_path, db, manifest)
    r = client.get("/operator/status")
    assert r.status_code == 200


def test_email_pipeline_operator_status_importable() -> None:
    """Guard: business logic must come from email-pipeline, not a fork."""
    from origenlab_email_pipeline.operator_status_report import build_operator_status_report

    assert callable(build_operator_status_report)
