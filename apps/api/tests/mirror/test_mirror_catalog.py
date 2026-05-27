"""Tests for GET /mirror/catalog/products (redacted Postgres mirror)."""

from __future__ import annotations

from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.postgres_dashboard_api.catalog import list_catalog_products

from conftest import _patch_mirror_postgres
from fake_catalog_conn import CatalogFakeConn

_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "evidence_email_id",
        "evidence_attachment_id",
        "transfer_id",
        "operation_id",
        "source_file",
        "source_path",
        "source_preview_path",
        "gmail_url",
        "notes",
        "body",
        "full_text",
        "email_body",
    }
)


@pytest.fixture
def catalog_mirror_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, CatalogFakeConn())
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


def test_mirror_list_catalog_products_returns_nine_seed_products(
    catalog_mirror_client: TestClient,
) -> None:
    r = catalog_mirror_client.get("/mirror/catalog/products", params={"limit": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert body["read_only"] is True
    assert body["data_source"] == "postgres_mirror"
    assert body["total"] == 9
    assert len(body["items"]) == 9
    assert "disclaimer" in body
    assert "espejo" in body["disclaimer"].lower() or "sqlite" in body["disclaimer"].lower()

    all_keys: set[str] = set()
    _collect_keys(body, all_keys)
    assert not (_FORBIDDEN_RESPONSE_KEYS & all_keys)


def test_mirror_detail_forbidden_keys_absent(catalog_mirror_client: TestClient) -> None:
    r = catalog_mirror_client.get("/mirror/catalog/products/crtop-olt-hp-5l")
    assert r.status_code == 200
    all_keys: set[str] = set()
    _collect_keys(r.json(), all_keys)
    assert not (_FORBIDDEN_RESPONSE_KEYS & all_keys)


def test_mirror_detail_crtop_specs_and_usd_exw(
    catalog_mirror_client: TestClient,
) -> None:
    r = catalog_mirror_client.get("/mirror/catalog/products/crtop-olt-hp-5l")
    assert r.status_code == 200
    product = r.json()["product"]
    assert product is not None
    assert product["display_name"].startswith("CRTOP")
    assert len(product["specs"]) >= 5
    assert "10600" not in (product.get("public_summary") or "")
    snap = next(s for s in product["price_snapshots"] if s["snapshot_key"] == "crtop-olt-hp-5l-exw-usd")
    assert snap["currency"] == "USD"
    assert snap["amount_decimal"] == "10600.00"
    assert snap["incoterm"] == "EXW"
    assert snap["is_public_safe"] is False


def test_mirror_catalog_spanish_prose_spacing(catalog_mirror_client: TestClient) -> None:
    serva = catalog_mirror_client.get("/mirror/catalog/products/serva-blueslick-250ml").json()
    assert "cotización y disponibilidad" in (serva["product"]["public_summary"] or "")

    ika = catalog_mirror_client.get("/mirror/catalog/products/ika-rv10-70-vapor-tube").json()[
        "product"
    ]
    assert "por cliente" in (ika["public_summary"] or "")
    assert "cantidad 3" in (ika["public_summary"] or "")
    assert "monto es" in (ika["supplier_offers"][0]["availability_note"] or "")
    snap = next(s for s in ika["price_snapshots"] if s["snapshot_key"] == "ika-rv10-70-price-ambiguous")
    assert "Monto 112,00" in (snap["price_notes"] or "")

    crtop = catalog_mirror_client.get("/mirror/catalog/products/crtop-olt-hp-5l").json()["product"]
    assert "antes de cotizar" in (crtop["public_summary"] or "")


def test_mirror_detail_ika_ambiguous_currency(
    catalog_mirror_client: TestClient,
) -> None:
    r = catalog_mirror_client.get("/mirror/catalog/products/ika-rv10-70-vapor-tube")
    assert r.status_code == 200
    product = r.json()["product"]
    assert product is not None
    assert product["display_name"] == "Tubo de vapor IKA RV10.70"
    snap = next(s for s in product["price_snapshots"] if s["snapshot_key"] == "ika-rv10-70-price-ambiguous")
    assert snap["currency"] is None
    assert snap["amount_decimal"] == "112.00"
    assert "ambigu" in (snap.get("price_notes") or "").lower()
    assert snap["quantity"] == "3"
    assert snap["is_public_safe"] is False


def test_mirror_catalog_product_not_found(catalog_mirror_client: TestClient) -> None:
    r = catalog_mirror_client.get("/mirror/catalog/products/unknown-product-key")
    assert r.status_code == 404


def test_filter_by_brand(catalog_mirror_client: TestClient) -> None:
    r = catalog_mirror_client.get("/mirror/catalog/products", params={"brand": "IKA", "limit": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["product_key"] == "ika-rv10-70-vapor-tube"


def test_filter_by_equipment_class(catalog_mirror_client: TestClient) -> None:
    r = catalog_mirror_client.get(
        "/mirror/catalog/products",
        params={"equipment_class": "reactor", "limit": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    keys = {item["product_key"] for item in body["items"]}
    assert keys == {"crtop-olt-hp-5l", "ollital-reactor-5l"}


def test_shared_list_matches_mirror_http(catalog_mirror_client: TestClient) -> None:
    fake = CatalogFakeConn()
    direct = list_catalog_products(fake, limit=100).model_dump(mode="json")
    http = catalog_mirror_client.get("/mirror/catalog/products", params={"limit": 100}).json()
    assert http["total"] == direct["total"] == 9
    assert {i["product_key"] for i in http["items"]} == {i["product_key"] for i in direct["items"]}


def test_mirror_catalog_openapi_paths(catalog_mirror_client: TestClient) -> None:
    paths = catalog_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/catalog/products" in paths
    assert "/mirror/catalog/products/{product_key}" in paths
