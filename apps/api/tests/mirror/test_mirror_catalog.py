"""Tests for GET /mirror/catalog/products (redacted Postgres mirror)."""

from __future__ import annotations

import json
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import get_settings
from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    FORBIDDEN_JOINED_PROSE_ARTIFACTS,
)
from origenlab_email_pipeline.postgres_dashboard_api.catalog import (
    _map_price_snapshot_row,
    _map_supplier_offer_row,
    list_catalog_products,
)

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


@pytest.fixture
def broken_prose_catalog_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    _patch_mirror_postgres(monkeypatch, CatalogFakeConn(broken_prose=True))
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


def test_mirror_api_json_has_no_joined_prose_artifacts(
    broken_prose_catalog_client: TestClient,
) -> None:
    payloads = [
        broken_prose_catalog_client.get("/mirror/catalog/products", params={"limit": 100}),
        broken_prose_catalog_client.get("/mirror/catalog/products/crtop-olt-hp-5l"),
        broken_prose_catalog_client.get("/mirror/catalog/products/ika-rv10-70-vapor-tube"),
    ]
    for response in payloads:
        assert response.status_code == 200
        blob = json.dumps(response.json(), ensure_ascii=False).lower()
        for artifact in FORBIDDEN_JOINED_PROSE_ARTIFACTS:
            assert artifact.lower() not in blob


def test_mirror_api_visible_prose_repairs_list_ika_and_crtop_detail(
    broken_prose_catalog_client: TestClient,
) -> None:
    list_body = broken_prose_catalog_client.get(
        "/mirror/catalog/products", params={"limit": 100}
    ).json()
    list_blob = json.dumps(list_body, ensure_ascii=False)
    assert "espejo Postgres" in list_body["disclaimer"]
    assert "la fuente" in list_body["disclaimer"]
    assert "cuerpos de correo" in list_body["disclaimer"]
    ika_list = next(
        i for i in list_body["items"] if i["product_key"] == "ika-rv10-70-vapor-tube"
    )
    assert ika_list["display_name"] == "Tubo de vapor IKA RV10.70"

    ika_body = broken_prose_catalog_client.get(
        "/mirror/catalog/products/ika-rv10-70-vapor-tube"
    ).json()
    ika_blob = json.dumps(ika_body, ensure_ascii=False)
    ika = ika_body["product"]
    assert ika is not None
    assert ika["display_name"] == "Tubo de vapor IKA RV10.70"
    assert ika["categories"][0]["display_name"] == "Accesorio de calentamiento"
    assert "vapor IKA" in ika_blob
    assert "de calentamiento" in ika_blob
    assert "monto es" in ika_blob
    assert "Monto 112,00" in ika_blob
    assert "antes de cotizar" in ika_blob

    crtop_body = broken_prose_catalog_client.get(
        "/mirror/catalog/products/crtop-olt-hp-5l"
    ).json()
    crtop_blob = json.dumps(crtop_body, ensure_ascii=False)
    assert "antes de cotizar" in (crtop_body["product"]["public_summary"] or "")
    for artifact in FORBIDDEN_JOINED_PROSE_ARTIFACTS:
        assert artifact.lower() not in crtop_blob.lower()
        assert artifact.lower() not in list_blob.lower()
        assert artifact.lower() not in ika_blob.lower()


def test_mirror_api_repairs_legacy_joined_prose_from_postgres(
    broken_prose_catalog_client: TestClient,
) -> None:
    list_body = broken_prose_catalog_client.get(
        "/mirror/catalog/products", params={"limit": 100}
    ).json()
    serva = next(
        i for i in list_body["items"] if i["product_key"] == "serva-blueslick-250ml"
    )
    assert "cotización y disponibilidad" in (serva["public_summary"] or "")

    ika_response = broken_prose_catalog_client.get(
        "/mirror/catalog/products/ika-rv10-70-vapor-tube"
    )
    assert ika_response.status_code == 200
    ika_blob = json.dumps(ika_response.json(), ensure_ascii=False)
    assert "monto es" in ika_blob
    assert "Monto 112,00" in ika_blob
    assert "antes de cotizar" in ika_blob

    ika = ika_response.json()["product"]
    assert "por cliente" in (ika["public_summary"] or "")
    assert "cantidad 3" in (ika["public_summary"] or "")
    assert "monto es" in (ika["supplier_offers"][0]["availability_note"] or "")
    snap = next(
        s for s in ika["price_snapshots"] if s["snapshot_key"] == "ika-rv10-70-price-ambiguous"
    )
    assert "Monto 112,00" in (snap["price_notes"] or "")
    assert "antes de cotizar" in (snap["price_notes"] or "")

    crtop = broken_prose_catalog_client.get(
        "/mirror/catalog/products/crtop-olt-hp-5l"
    ).json()["product"]
    assert "antes de cotizar" in (crtop["public_summary"] or "")


def test_mapper_repairs_nested_prose_when_row_mutation_is_ignored() -> None:
    """Regression: in-place row edits must not be required for nested prose repair."""

    class _ReadOnlyRow:
        def __init__(self, data: dict[str, str]) -> None:
            self._data = data

        def items(self):
            return self._data.items()

        def get(self, key: str, default: object = None) -> object:
            return self._data.get(key, default)

        def __getitem__(self, key: str) -> str:
            return self._data[key]

    row = _ReadOnlyRow(
        {
            "offer_key": "ika-rv10-70-rg-energia-quote",
            "supplier_org_name": "IKA",
            "supplier_domain": "ika.net.br",
            "offer_status": "needs_review",
            "quoted_at": None,
            "valid_until": None,
            "incoterm": None,
            "payment_terms": None,
            "delivery_terms": None,
            "currency": None,
            "quantity_offered": "1",
            "availability_note": (
                "Stock disponible según proveedor; confirmar moneda y si el montoes precio unitario."
            ),
            "confidence": "extracted_needs_review",
        }
    )
    offer = _map_supplier_offer_row(row)
    assert "monto es" in (offer.availability_note or "")

    snap_row = _ReadOnlyRow(
        {
            "snapshot_key": "ika-rv10-70-price-ambiguous",
            "snapshot_kind": "supplier_quote",
            "offer_key": "ika-rv10-70-rg-energia-quote",
            "currency": None,
            "amount_decimal": "112.00",
            "amount_minor": None,
            "amount_clp_integer": None,
            "quantity": "3",
            "unit": "ea",
            "incoterm": None,
            "price_notes": (
                "Cliente solicitó cantidad3. Monto112,00 del proveedor; confirmar antes decotizar."
            ),
            "is_public_safe": False,
            "confidence": "extracted_needs_review",
            "observed_at": "2026-05-27T00:00:00Z",
        }
    )
    snap = _map_price_snapshot_row(snap_row)
    assert "Monto 112,00" in (snap.price_notes or "")
    assert "antes de cotizar" in (snap.price_notes or "")


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
