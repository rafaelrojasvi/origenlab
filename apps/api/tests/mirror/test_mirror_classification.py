"""Tests for GET /mirror/classification/* (legacy /classification/* parity)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.postgres_dashboard_api.classification import (
    classification_summary,
)

from conftest import _patch_mirror_postgres
from fake_classification_conn import ClassificationFakeConn


@pytest.fixture
def classification_mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, ClassificationFakeConn())
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_mirror_classification_summary(classification_mirror_client: TestClient) -> None:
    r = classification_mirror_client.get("/mirror/classification/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["table_available"] is True
    assert body["status"] == "ok"
    assert body["kpi"]["posibles_solicitudes"] == 1
    assert body["kpi"]["cotizaciones_enviadas"] == 1
    assert body["kpi"]["posibles_compras"] == 1


def test_mirror_classification_recent_filter(
    classification_mirror_client: TestClient,
) -> None:
    r = classification_mirror_client.get(
        "/mirror/classification/recent",
        params={"label": "purchase_or_order_signal", "limit": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert len(body["items"]) == 1
    assert body["items"][0]["predicted_label"] == "purchase_or_order_signal"


def test_mirror_classification_actions(classification_mirror_client: TestClient) -> None:
    r = classification_mirror_client.get("/mirror/classification/actions")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert len(body["groups"]) >= 2


def test_shared_classification_summary_matches_http(
    classification_mirror_client: TestClient,
) -> None:
    fake = ClassificationFakeConn()
    direct = classification_summary(fake).model_dump(mode="json")
    http = classification_mirror_client.get("/mirror/classification/summary").json()
    assert set(http.keys()) == set(direct.keys())
    assert http["status"] == direct["status"] == "ok"


def test_mirror_classification_missing_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    from fake_conn import MirrorFakeConn

    fake = MirrorFakeConn()
    fake.tables[("reporting", "email_classification_canonical")] = False
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, fake)
    with TestClient(create_app()) as client:
        r = client.get("/mirror/classification/summary")
    assert r.json()["table_available"] is False
    assert r.json()["status"] == "missing_table"
    get_settings.cache_clear()


def test_mirror_classification_openapi_paths(
    classification_mirror_client: TestClient,
) -> None:
    paths = classification_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/classification/summary" in paths
    assert "/mirror/classification/recent" in paths
    assert "/mirror/classification/actions" in paths
