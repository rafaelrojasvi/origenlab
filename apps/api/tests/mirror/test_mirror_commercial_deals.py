"""Tests for GET /mirror/commercial/deals (redacted Postgres mirror)."""

from __future__ import annotations

from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.postgres_dashboard_api.commercial_deals import (
    get_commercial_deal,
    list_commercial_deals,
)

from conftest import _patch_mirror_postgres
from fake_commercial_deals_conn import CommercialDealsFakeConn

_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "transfer_id",
        "operation_id",
        "source_preview_path",
        "source_preview_sha256",
        "notes_json",
        "operator_private_json",
        "margin_notes",
        "client_contact_email",
        "supplier_contact_email",
        "client_domain",
        "supplier_domain",
        "client_po_number",
        "client_invoice_number",
        "extract_snippet",
        "operator_note",
        "gmail_url",
        "legacy_purchase_event_id",
        "ref_code",
        "description",
        "counterparty_email",
        "subject",
        "source_path",
        "source_file",
    }
)


@pytest.fixture
def commercial_deals_mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, CommercialDealsFakeConn())
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def _collect_keys(obj: object, keys: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k))
            _collect_keys(v, keys)
    elif isinstance(obj, list):
        for item in obj:
            _collect_keys(item, keys)


def test_mirror_list_commercial_deals_returns_redacted_row(
    commercial_deals_mirror_client: TestClient,
) -> None:
    r = commercial_deals_mirror_client.get("/mirror/commercial/deals")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert body["read_only"] is True
    assert body["data_source"] == "postgres_mirror"
    assert body["total"] == 1
    item = body["items"][0]
    assert item["deal_key"] == "serva-ceaf-oc-26172-po-174-26"
    assert "CEAF" in item["client_org_name"]
    assert item["margin_status"] == "needs_review"
    assert item["margin_net_clp"] is None
    assert isinstance(item["margin_blockers"], list)

    all_keys: set[str] = set()
    _collect_keys(body, all_keys)
    assert not (_FORBIDDEN_RESPONSE_KEYS & all_keys)


def test_mirror_get_commercial_deal_by_key(
    commercial_deals_mirror_client: TestClient,
) -> None:
    r = commercial_deals_mirror_client.get(
        "/mirror/commercial/deals/serva-ceaf-oc-26172-po-174-26"
    )
    assert r.status_code == 200
    deal = r.json()["deal"]
    assert deal is not None
    assert deal["supplier_amount_paid_decimal"] == "218.00"
    assert deal["supplier_invoice_total_minor"] == 36300


def test_mirror_commercial_deal_not_found(
    commercial_deals_mirror_client: TestClient,
) -> None:
    r = commercial_deals_mirror_client.get("/mirror/commercial/deals/nonexistent-deal")
    assert r.status_code == 404


def test_shared_list_matches_mirror_http(
    commercial_deals_mirror_client: TestClient,
) -> None:
    fake = CommercialDealsFakeConn()
    direct = list_commercial_deals(fake, limit=20).model_dump(mode="json")
    http = commercial_deals_mirror_client.get("/mirror/commercial/deals").json()
    assert http["items"][0]["deal_key"] == direct["items"][0]["deal_key"]


def test_mirror_commercial_deals_openapi_paths(
    commercial_deals_mirror_client: TestClient,
) -> None:
    paths = commercial_deals_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/commercial/deals" in paths
    assert "/mirror/commercial/deals/{deal_key}" in paths
