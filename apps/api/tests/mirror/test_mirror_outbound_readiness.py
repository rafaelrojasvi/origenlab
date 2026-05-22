"""Tests for GET /mirror/outbound/readiness (legacy /outbound/readiness parity)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from origenlab_email_pipeline.postgres_dashboard_api.outbound_readiness import (
    assess_postgres_outbound_readiness,
)

from fake_conn import MirrorFakeConn


@pytest.fixture
def readiness_mirror_client(summary_mirror_client: TestClient) -> TestClient:
    return summary_mirror_client


def test_mirror_outbound_readiness_shape(readiness_mirror_client: TestClient) -> None:
    r = readiness_mirror_client.get("/mirror/outbound/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["eventually_consistent"] is True
    assert body["data_source"] == "postgres_mirror"
    assert "disclaimer" in body
    assert body["verdict"] in ("ready", "ready_with_warnings", "not_ready")
    assert "warnings" in body
    assert "errors" in body
    assert "tables" in body
    assert "mart.contact_master" in body["tables"]


def test_mirror_outbound_readiness_max_staleness_query_param(
    readiness_mirror_client: TestClient,
) -> None:
    r = readiness_mirror_client.get(
        "/mirror/outbound/readiness", params={"max_staleness_days": 14}
    )
    assert r.status_code == 200


def test_shared_outbound_readiness_matches_mirror_http(
    readiness_mirror_client: TestClient,
) -> None:
    fake = MirrorFakeConn()
    direct = assess_postgres_outbound_readiness(
        fake,
        postgres_url_redacted="postgresql://u:***@localhost:5432/scratch",
        gmail_user="contacto@origenlab.cl",
    ).model_dump(mode="json")
    http = readiness_mirror_client.get("/mirror/outbound/readiness").json()
    assert set(http.keys()) == set(direct.keys())
    assert http["verdict"] == direct["verdict"]
    assert http["data_source"] == "postgres_mirror"


def test_mirror_outbound_readiness_openapi_path(
    readiness_mirror_client: TestClient,
) -> None:
    paths = readiness_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/outbound/readiness" in paths
    assert "get" in paths["/mirror/outbound/readiness"]


def test_operator_status_unchanged_with_default_sqlite() -> None:
    """Operator plane must not depend on mirror Postgres mocks."""
    from origenlab_api.main import create_app

    with TestClient(create_app()) as client:
        r = client.get("/operator/status")
    assert r.status_code == 200
    assert "verdict" in r.json()
