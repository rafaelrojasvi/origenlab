"""Tests for /mirror/health/dependencies and /mirror/meta/dashboard-sync."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.postgres_dashboard_api.health import (
    build_health_dependencies_response,
)
from origenlab_email_pipeline.postgres_dashboard_api.queries import latest_dashboard_sync


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class MetaFakeConn:
    """Minimal psycopg-like connection for mirror metadata queries."""

    def __init__(
        self,
        *,
        sync_table: bool = False,
        sync_row: dict[str, Any] | None = None,
    ) -> None:
        self.tables: dict[tuple[str, str], bool] = {
            ("reporting", "dashboard_sync_run"): sync_table,
        }
        self._sync_row = sync_row

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "information_schema.tables" in s:
            schema = params[0]
            table = params[1]
            ok = self.tables.get((schema, table), False)
            return _FakeCursor([{"?": 1}] if ok else [])
        if "select 1" in s and "information_schema" not in s:
            return _FakeCursor([{"?": 1}])
        if "from reporting.dashboard_sync_run" in s:
            if self._sync_row is not None:
                return _FakeCursor([self._sync_row])
            return _FakeCursor([])
        return _FakeCursor([])


def _pg_ctx(fake: MetaFakeConn):
    @contextmanager
    def _fake_pg(_url: str) -> Generator[MetaFakeConn, None, None]:
        yield fake

    return _fake_pg


@pytest.fixture
def mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    fake = MetaFakeConn()
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        _pg_ctx(fake),
    )
    monkeypatch.setattr(
        "origenlab_api.mirror.deps.postgres_connection",
        _pg_ctx(fake),
    )
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_mirror_health_dependencies_shape(mirror_client: TestClient) -> None:
    r = mirror_client.get("/mirror/health/dependencies")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded", "error")
    assert isinstance(body["dependencies"], list)
    names = {d["name"] for d in body["dependencies"]}
    assert "postgres" in names
    assert "sqlite" in names
    assert "note" in body


def test_mirror_dashboard_sync_missing_table(mirror_client: TestClient) -> None:
    r = mirror_client.get("/mirror/meta/dashboard-sync")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is False
    assert body["status"] == "missing_table"


def test_mirror_dashboard_sync_latest_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    started = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 5, 15, 10, 0, 2, tzinfo=timezone.utc)
    row = {
        "id": 42,
        "started_at": started,
        "finished_at": finished,
        "status": "success",
        "canonical_contact_count": 10,
        "canonical_organization_count": 5,
        "canonical_opportunity_signal_count": 3,
        "archive_contact_count": 100,
        "archive_organization_count": 50,
        "archive_opportunity_signal_count": 20,
        "email_suppression_count": 1,
        "domain_suppression_count": 0,
        "outreach_state_count": 2,
        "error_message": None,
    }
    fake = MetaFakeConn(sync_table=True, sync_row=row)
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        _pg_ctx(fake),
    )
    monkeypatch.setattr("origenlab_api.mirror.deps.postgres_connection", _pg_ctx(fake))
    with TestClient(create_app()) as client:
        r = client.get("/mirror/meta/dashboard-sync")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["latest_sync_id"] == 42
    assert body["elapsed_seconds"] == 2.0
    assert "postgres_mirror_note" in body


def test_shared_query_matches_http_mirror_meta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    """Direct shared query and /mirror/meta should serialize the same shape."""
    row = {
        "id": 7,
        "started_at": datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 5, 1, 12, 0, 1, tzinfo=timezone.utc),
        "status": "dry_run",
        "canonical_contact_count": 1,
        "canonical_organization_count": 1,
        "canonical_opportunity_signal_count": 0,
        "archive_contact_count": 0,
        "archive_organization_count": 0,
        "archive_opportunity_signal_count": 0,
        "email_suppression_count": 0,
        "domain_suppression_count": 0,
        "outreach_state_count": 0,
        "error_message": None,
    }
    fake = MetaFakeConn(sync_table=True, sync_row=row)
    direct = latest_dashboard_sync(fake).model_dump(mode="json")

    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    monkeypatch.setattr("origenlab_api.mirror.deps.postgres_connection", _pg_ctx(fake))
    with TestClient(create_app()) as client:
        http = client.get("/mirror/meta/dashboard-sync").json()

    assert set(http.keys()) == set(direct.keys())
    assert http["status"] == direct["status"] == "dry_run"
    assert http["latest_sync_id"] == direct["latest_sync_id"] == 7


def test_health_dependencies_shared_matches_mirror_http(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    fake = MetaFakeConn()
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    ctx = _pg_ctx(fake)
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        ctx,
    )
    direct = build_health_dependencies_response(
        postgres_url="postgresql://u:p@localhost:5432/scratch",
        postgres_url_redacted="postgresql://u:***@localhost:5432/scratch",
        sqlite_path=sqlite,
    ).model_dump(mode="json")

    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    with TestClient(create_app()) as client:
        http = client.get("/mirror/health/dependencies").json()

    assert set(http.keys()) == set(direct.keys())
    assert {d["name"] for d in http["dependencies"]} == {
        d["name"] for d in direct["dependencies"]
    }
