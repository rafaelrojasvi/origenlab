"""Optional integration smoke for /mirror on disposable Postgres only."""

from __future__ import annotations

import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings


@pytest.mark.skipif(
    not (os.environ.get("ORIGENLAB_TEST_POSTGRES_URL") or "").strip(),
    reason="Set ORIGENLAB_TEST_POSTGRES_URL for disposable Postgres integration.",
)
def test_mirror_health_and_meta_integration() -> None:
    url = os.environ["ORIGENLAB_TEST_POSTGRES_URL"].strip()
    get_settings.cache_clear()
    os.environ["ORIGENLAB_POSTGRES_URL"] = url
    try:
        with TestClient(create_app()) as client:
            health = client.get("/mirror/health/dependencies")
            if health.status_code == 503:
                pytest.skip(f"Postgres not reachable: {health.json()}")
            assert health.status_code == 200
            assert health.json()["status"] in ("ok", "degraded", "error")

            meta = client.get("/mirror/meta/dashboard-sync")
            assert meta.status_code == 200
            body = meta.json()
            assert "table_available" in body
            assert "status" in body
            assert "postgres_mirror_note" in body

            readiness = client.get("/mirror/outbound/readiness")
            assert readiness.status_code == 200
            ready_body = readiness.json()
            assert ready_body["data_source"] == "postgres_mirror"
            assert ready_body["verdict"] in (
                "ready",
                "ready_with_warnings",
                "not_ready",
                "unknown",
            )
    finally:
        get_settings.cache_clear()
