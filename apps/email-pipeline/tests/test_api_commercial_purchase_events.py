"""Tests for read-only /commercial/purchase-events endpoints (mocked Postgres)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.config import reset_api_settings_cache
from origenlab_api.main import create_app
from test_api_slice1 import FakeConn, _FakeCursor


class CommercialFakeConn(FakeConn):
    def __init__(self) -> None:
        super().__init__()
        self.tables[("commercial", "purchase_event")] = True
        self.tables[("commercial", "purchase_event_item")] = True
        self.purchase_events: list[dict[str, Any]] = [
            {
                "id": 1,
                "source_email_id": 710387,
                "buyer_org_name": "Centro de Estudios Avanzados en Fruticultura CEAF",
                "buyer_contact_name": "Carlos Garay Sotelo",
                "buyer_contact_email": "cgaray@ceaf.cl",
                "buyer_domain": "ceaf.cl",
                "purchase_status": "purchase_order_received",
                "oc_number": "26172",
                "quote_number": "011728A-26",
                "project_name": "ANID",
                "project_code": "R23F0002",
                "net_amount_clp": 1_260_000,
                "iva_amount_clp": 239_400,
                "gross_amount_clp": 1_499_400,
                "currency": "CLP",
                "email_date_iso": "2026-05-14T12:30:18-04:00",
                "email_subject": "Remite OC N º 26172",
                "commercial_summary": "CEAF OC 26172",
                "dispatch_requested": True,
                "invoice_requested": True,
                "bank_details_requested": True,
            }
        ]
        self.purchase_items: list[dict[str, Any]] = [
            {
                "purchase_event_id": 1,
                "line_number": 1,
                "ref_code": "4250001",
                "product_name": "BlueSlick™ 250 ml",
                "brand": "SERVA",
                "quantity": None,
                "net_amount_clp": 695_000,
                "evidence_source": "oc_attachment",
            },
            {
                "purchase_event_id": 1,
                "line_number": 2,
                "ref_code": "3593002",
                "product_name": "N,N,N',N'-Tetramethyl-ethylenediamine, 25 ml",
                "brand": "SERVA",
                "quantity": None,
                "net_amount_clp": 545_000,
                "evidence_source": "oc_attachment",
            },
        ]

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "from commercial.purchase_event_item" in s and "purchase_event_id in" in s:
            ids = list(params or ())
            rows = [r for r in self.purchase_items if int(r["purchase_event_id"]) in ids]
            return _FakeCursor(rows)
        if "from commercial.purchase_event" in s and "where id" in s:
            eid = int(params[0])
            rows = [r for r in self.purchase_events if int(r["id"]) == eid]
            return _FakeCursor(rows)
        if "from commercial.purchase_event" in s and "order by" in s:
            return _FakeCursor(self.purchase_events)
        if "count(*)" in s and "commercial.purchase_event" in s:
            return _FakeCursor([{"n": len(self.purchase_events)}])
        return super().execute(sql, params)


@contextmanager
def client_with_conn(conn: CommercialFakeConn) -> Generator[TestClient, None, None]:
    reset_api_settings_cache()
    app = create_app()

    def override() -> CommercialFakeConn:
        return conn

    from origenlab_api.deps import get_db_conn

    app.dependency_overrides[get_db_conn] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        reset_api_settings_cache()


def test_list_purchase_events_returns_ceaf() -> None:
    conn = CommercialFakeConn()
    with client_with_conn(conn) as client:
        res = client.get("/commercial/purchase-events")
    assert res.status_code == 200
    body = res.json()
    assert body["table_available"] is True
    assert body["total"] == 1
    item = body["items"][0]
    assert "CEAF" in item["buyer_org_name"]
    assert item["oc_number"] == "26172"
    assert item["net_amount_clp"] == 1_260_000
    assert item["gross_amount_clp"] == 1_499_400
    assert len(item["line_items"]) == 2
    assert "BlueSlick" in item["product_summary"]


def test_get_purchase_event_by_id() -> None:
    conn = CommercialFakeConn()
    with client_with_conn(conn) as client:
        res = client.get("/commercial/purchase-events/1")
    assert res.status_code == 200
    ev = res.json()["event"]
    assert ev is not None
    assert ev["buyer_contact_email"] == "cgaray@ceaf.cl"
    assert ev["purchase_status_label_es"] == "OC recibida"
