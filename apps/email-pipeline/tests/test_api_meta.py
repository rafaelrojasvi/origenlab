"""Tests for GET /meta/dashboard-sync."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from origenlab_api.config import reset_api_settings_cache
from origenlab_api.main import create_app
from test_api_slice1 import FakeConn, _FakeCursor


class MetaFakeConn(FakeConn):
    """FakeConn with reporting.dashboard_sync_run support."""

    def __init__(
        self,
        *,
        sync_table: bool = False,
        sync_row: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.tables[("reporting", "dashboard_sync_run")] = sync_table
        self._sync_row = sync_row

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "from reporting.dashboard_sync_run" in s:
            if self._sync_row is not None:
                return _FakeCursor([self._sync_row])
            return _FakeCursor([])
        return super().execute(sql, params)


@pytest.fixture
def meta_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Generator[TestClient, None, None]:
    reset_api_settings_cache()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    yield from _client_with_conn(monkeypatch, MetaFakeConn())


def _client_with_conn(
    monkeypatch: pytest.MonkeyPatch, fake: MetaFakeConn
) -> Generator[TestClient, None, None]:
    @contextmanager
    def _fake_pg(_url: str) -> Generator[MetaFakeConn, None, None]:
        yield fake

    monkeypatch.setattr("origenlab_api.deps.postgres_connection", _fake_pg)
    monkeypatch.setattr("origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection", _fake_pg)
    app = create_app()
    with TestClient(app) as tc:
        yield tc
    reset_api_settings_cache()


def test_dashboard_sync_missing_table(meta_client: TestClient) -> None:
    r = meta_client.get("/meta/dashboard-sync")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is False
    assert body["status"] == "missing_table"
    assert body["latest_sync_id"] is None


def _pg_ctx(fake: MetaFakeConn):
    @contextmanager
    def _fake_pg(_url: str) -> Generator[MetaFakeConn, None, None]:
        yield fake

    return _fake_pg


def test_dashboard_sync_no_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    fake = MetaFakeConn(sync_table=True, sync_row=None)
    reset_api_settings_cache()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    monkeypatch.setattr("origenlab_api.deps.postgres_connection", _pg_ctx(fake))
    monkeypatch.setattr("origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection", _pg_ctx(fake))
    with TestClient(create_app()) as client:
        r = client.get("/meta/dashboard-sync")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert body["status"] == "no_rows"


def test_dashboard_sync_latest_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    started = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 5, 15, 10, 0, 2, tzinfo=timezone.utc)
    row = {
        "id": 42,
        "started_at": started,
        "finished_at": finished,
        "status": "success",
        "canonical_contact_count": 497,
        "canonical_organization_count": 261,
        "canonical_opportunity_signal_count": 200,
        "archive_contact_count": 27198,
        "archive_organization_count": 10688,
        "archive_opportunity_signal_count": 2705,
        "email_suppression_count": 2,
        "domain_suppression_count": 1,
        "outreach_state_count": 4,
        "error_message": None,
    }
    fake = MetaFakeConn(sync_table=True, sync_row=row)
    reset_api_settings_cache()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    monkeypatch.setattr("origenlab_api.deps.postgres_connection", _pg_ctx(fake))
    monkeypatch.setattr("origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection", _pg_ctx(fake))
    with TestClient(create_app()) as client:
        r = client.get("/meta/dashboard-sync")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert body["status"] == "success"
    assert body["latest_sync_id"] == 42
    assert body["elapsed_seconds"] == 2.0
    assert "postgres_mirror_note" in body
    assert body["canonical_contact_count"] == 497
    assert body["archive_contact_count"] == 27198
    assert body["email_suppression_count"] == 2
    assert body["outreach_state_count"] == 4
    assert body["error_message"] is None
