"""Tests for GET /mirror/contacts and GET /mirror/organizations (legacy parity)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.operational_scope import (
    ARCHIVE_SCOPE_NOTE,
    CANONICAL_SCOPE_NOTE,
)
from origenlab_email_pipeline.postgres_dashboard_api.mart_lists import (
    list_contacts,
    list_organizations,
)

from conftest import _patch_mirror_postgres
from fake_conn import SCRATCH_ARCHIVE, SCRATCH_CANONICAL
from fake_mart_conn import MartListsFakeConn


@pytest.fixture
def mart_mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, MartListsFakeConn())
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_mirror_contacts_pagination_default_canonical(
    mart_mirror_client: TestClient,
) -> None:
    r = mart_mirror_client.get("/mirror/contacts", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["scope_available"] is True
    assert body["scope_note"] == CANONICAL_SCOPE_NOTE
    assert body["table_available"] is True
    assert body["items"][0]["email"] == "lab@example.cl"
    assert body["total"] == SCRATCH_CANONICAL["mart.contact_master_canonical"]


def test_mirror_contacts_archive_scope(mart_mirror_client: TestClient) -> None:
    r = mart_mirror_client.get("/mirror/contacts", params={"scope": "archive", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "archive"
    assert body["scope_note"] == ARCHIVE_SCOPE_NOTE
    assert body["items"][0]["email"] == "archive@example.cl"
    assert body["total"] == SCRATCH_ARCHIVE["mart.contact_master"]


def test_mirror_organizations_default_canonical(
    mart_mirror_client: TestClient,
) -> None:
    r = mart_mirror_client.get("/mirror/organizations", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["scope_available"] is True
    assert body["scope_note"] == CANONICAL_SCOPE_NOTE
    assert body["items"][0]["domain"] == "lab.cl"
    assert body["total"] == SCRATCH_CANONICAL["mart.organization_master_canonical"]


def test_mirror_organizations_archive_scope(mart_mirror_client: TestClient) -> None:
    r = mart_mirror_client.get(
        "/mirror/organizations", params={"scope": "archive", "limit": 5}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "archive"
    assert body["items"][0]["domain"] == "archive.cl"
    assert body["total"] == SCRATCH_ARCHIVE["mart.organization_master"]


def test_shared_list_matches_mirror_http_contacts(
    mart_mirror_client: TestClient,
) -> None:
    fake = MartListsFakeConn()
    direct = list_contacts(fake, limit=10, offset=0, domain=None, q=None).model_dump(
        mode="json"
    )
    http = mart_mirror_client.get("/mirror/contacts", params={"limit": 10}).json()
    assert http["items"][0]["email"] == direct["items"][0]["email"] == "lab@example.cl"


def test_mirror_mart_openapi_paths(mart_mirror_client: TestClient) -> None:
    paths = mart_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/contacts" in paths
    assert "/mirror/organizations" in paths
    assert "/contacts/{email}" in paths
    assert "/mirror/contacts/{email}" not in paths


def test_mirror_contacts_list_does_not_capture_operator_contact_detail(
    mart_mirror_client: TestClient, tmp_path: Path
) -> None:
    """GET /mirror/contacts is a list; GET /contacts/{email} stays operator SQLite detail."""
    list_r = mart_mirror_client.get("/mirror/contacts", params={"limit": 5})
    assert list_r.status_code == 200
    assert "items" in list_r.json()
    assert "contact" not in list_r.json()

    from test_contacts_detail import _client as contact_detail_client

    db = tmp_path / "intel.sqlite"
    detail = contact_detail_client(tmp_path, db).get("/contacts/known@cliente.cl")
    assert detail.status_code == 200
    body = detail.json()
    assert body["contact"]["normalized_email"] == "known@cliente.cl"
    assert body["meta"]["data_source"] == "sqlite"


def test_mirror_contacts_route_is_get_only(mart_mirror_client: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        r = getattr(mart_mirror_client, method)("/mirror/contacts")
        assert r.status_code == 405
