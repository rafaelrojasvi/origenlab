"""Tests for GET /mirror/commercial/purchase-events (legacy parity)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.postgres_dashboard_api.commercial_purchase import (
    get_commercial_purchase_event,
    list_commercial_purchase_events,
)

from conftest import _patch_mirror_postgres
from fake_commercial_conn import CommercialFakeConn


@pytest.fixture
def commercial_mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, CommercialFakeConn())
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_mirror_list_purchase_events_returns_ceaf(
    commercial_mirror_client: TestClient,
) -> None:
    r = commercial_mirror_client.get("/mirror/commercial/purchase-events")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert body["total"] == 1
    item = body["items"][0]
    assert "CEAF" in item["buyer_org_name"]
    assert item["oc_number"] == "26172"
    assert item["net_amount_clp"] == 1_260_000
    assert len(item["line_items"]) == 2
    assert "BlueSlick" in item["product_summary"]


def test_mirror_get_purchase_event_by_id(commercial_mirror_client: TestClient) -> None:
    r = commercial_mirror_client.get("/mirror/commercial/purchase-events/1")
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev is not None
    assert ev["buyer_contact_email"] == "cgaray@ceaf.cl"
    assert ev["purchase_status_label_es"] == "OC recibida"


def test_mirror_purchase_event_not_found(commercial_mirror_client: TestClient) -> None:
    r = commercial_mirror_client.get("/mirror/commercial/purchase-events/999")
    assert r.status_code == 404


def test_shared_list_matches_mirror_http(commercial_mirror_client: TestClient) -> None:
    fake = CommercialFakeConn()
    direct = list_commercial_purchase_events(fake, limit=20).model_dump(mode="json")
    http = commercial_mirror_client.get("/mirror/commercial/purchase-events").json()
    assert set(http.keys()) == set(direct.keys())
    assert http["items"][0]["oc_number"] == direct["items"][0]["oc_number"] == "26172"


def test_mirror_commercial_openapi_paths(commercial_mirror_client: TestClient) -> None:
    paths = commercial_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/commercial/purchase-events" in paths
    assert "/mirror/commercial/purchase-events/{event_id}" in paths
