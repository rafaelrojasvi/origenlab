"""Shared fixtures for mirror route tests (mocked Postgres)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings

from fake_conn import MirrorFakeConn, SummaryFakeConn


def _pg_ctx(fake: SummaryFakeConn | MirrorFakeConn):
    @contextmanager
    def _fake_pg(_url: str) -> Generator[SummaryFakeConn | MirrorFakeConn, None, None]:
        yield fake

    return _fake_pg


def _patch_mirror_postgres(monkeypatch: pytest.MonkeyPatch, fake: MirrorFakeConn) -> None:
    ctx = _pg_ctx(fake)
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        ctx,
    )
    monkeypatch.setattr("origenlab_api.mirror.deps.postgres_connection", ctx)
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.db.postgres_connection",
        ctx,
    )


@pytest.fixture
def summary_mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, MirrorFakeConn())
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()
