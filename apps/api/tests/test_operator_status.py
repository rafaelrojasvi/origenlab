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


def _client_with_settings(tmp_path: Path, db: Path | None, manifest: dict | None) -> TestClient:
    active = tmp_path / "current"
    active.mkdir(parents=True)
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (active / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(
        sqlite_path=db,
        active_current=active,
    )
    app = create_app()
    app.dependency_overrides.clear()

    from origenlab_api.settings import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_operator_status_response_stable_keys(tmp_path: Path) -> None:
    """Lock API-0 JSON shape for operator status."""
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, source_file TEXT, folder TEXT)"
    )
    conn.commit()
    conn.close()
    manifest = {
        "known_warnings": [],
        "canonical_files": [],
        "campaign_mode": "equipment_first",
        "current_operator_focus": "focus",
    }
    client = _client_with_settings(tmp_path, db, manifest)
    data = client.get("/operator/status").json()
    assert set(data.keys()) == {
        "verdict",
        "sqlite_path",
        "campaign_mode",
        "operator_focus",
        "outbound_readiness",
        "warnings",
    }
    assert isinstance(data["warnings"], list)
    assert isinstance(data["outbound_readiness"], str)


def test_operator_status_read_only_minimal_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, source_file TEXT, folder TEXT)"
    )
    conn.commit()
    conn.close()

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
    assert set(data.keys()) == {
        "verdict",
        "sqlite_path",
        "campaign_mode",
        "operator_focus",
        "outbound_readiness",
        "warnings",
    }


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


def test_operator_status_no_postgres_env_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)

    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, source_file TEXT, folder TEXT)"
    )
    conn.commit()
    conn.close()

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
