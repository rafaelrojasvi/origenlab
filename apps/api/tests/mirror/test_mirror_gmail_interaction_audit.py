"""GET /mirror/audits/gmail-interactions — read-only snapshot route."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.settings import get_settings


def _client(monkeypatch: pytest.MonkeyPatch, kv_row: dict[str, Any] | None) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")

    def _fake_snapshot(_settings: Any) -> dict[str, Any] | None:
        return kv_row

    monkeypatch.setattr(
        "origenlab_api.mirror.routes.audits.snapshot_repo.get_gmail_interaction_audit_snapshot",
        _fake_snapshot,
    )
    from origenlab_api.main import create_app

    return TestClient(create_app())


def test_snapshot_missing_returns_safe_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, None)
    res = client.get("/mirror/audits/gmail-interactions")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "snapshot_missing"
    assert data["message"] == "snapshot_missing"
    assert data["snapshot"] is None
    assert data["read_only"] is True


def test_snapshot_exists_returns_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    kv_row = {
        "updated_at": now.isoformat(),
        "snapshot": {
            "schema_version": 1,
            "generated_at_utc": now.isoformat(),
            "source": "sqlite:gmail:contacto",
            "lookback_days": 180,
            "domains": [
                {
                    "domain": "ika.net.br",
                    "message_count": 9,
                    "sent_count": 5,
                    "received_count": 4,
                    "thread_count": 1,
                    "latest_email_at": now.isoformat(),
                    "latest_subject_safe": "RE: CONSULTA",
                    "has_attachments": True,
                    "matched_aliases": ["ika.net.br"],
                }
            ],
        },
    }
    client = _client(monkeypatch, kv_row)
    res = client.get("/mirror/audits/gmail-interactions")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["source"] == "postgres_snapshot"
    assert data["snapshot"]["domains"][0]["message_count"] == 9


def test_snapshot_stale_flag_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    kv_row = {
        "updated_at": old.isoformat(),
        "snapshot": {
            "schema_version": 1,
            "generated_at_utc": old.isoformat(),
            "source": "sqlite:gmail:contacto",
            "lookback_days": 180,
            "domains": [],
        },
    }
    client = _client(monkeypatch, kv_row)
    res = client.get("/mirror/audits/gmail-interactions")
    data = res.json()
    assert data["snapshot_stale"] is True
