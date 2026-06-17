"""GET /opportunities/equipment — equipment-first operator queue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import Settings

_OPERATOR_HEADER = (
    "priority_rank,codigo_licitacion,buyer,region,close_date,equipment_category,"
    "item_description,next_action,contact_status,safe_channel,supplier_needed,"
    "supplier_contact,gmail_prior_thread,outreach_state,operator_note\n"
)


def _fixture_csv(active: Path) -> None:
    rows = (
        "1,LP-001,Buyer One,RM,01/06/2026,centrifuge,Centrifuge unit,quote_now,"
        "no_verified_buyer_email,mercado_publico_bid,yes,Sup,,,fit=90\n"
        "2,LP-002,Buyer Two,Valpo,02/06/2026,balance,Balance service,needs_supplier_quote,"
        "no_verified_buyer_email,supplier_quote_request,yes,Sup,,,fit=80\n"
        "3,LP-003,Buyer Three,RM,03/06/2026,incubator,Monitor only,account_intelligence_only,"
        "n/a,account_intelligence_only,no,,,intel only\n"
    )
    (active / "equipment_first_operator_queue_20260518.csv").write_text(
        _OPERATOR_HEADER + rows,
        encoding="utf-8",
    )
    (active / "buyer_opportunity_crosscheck_20260518.csv").write_text(
        "priority_rank,codigo_licitacion\n99,STALE\n",
        encoding="utf-8",
    )
    manifest = {
        "campaign_mode": "equipment_first",
        "canonical_files": [
            "equipment_first_operator_queue_20260518.csv",
            "buyer_opportunity_crosscheck_20260518.csv",
        ],
        "stale_files": [{"path": "buyer_opportunity_crosscheck_20260518.csv"}],
    }
    (active / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _client(tmp_path: Path, *, with_csv: bool = True) -> TestClient:
    active = tmp_path / "current"
    active.mkdir(parents=True)
    if with_csv:
        _fixture_csv(active)
    else:
        (active / "manifest.json").write_text(
            json.dumps({"campaign_mode": "equipment_first", "canonical_files": []}),
            encoding="utf-8",
        )
    app = create_app()
    from origenlab_api.settings import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(active_current=active)
    return TestClient(app)


def test_opportunities_equipment_returns_200(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.get("/opportunities/equipment")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["data_source"] == "active_current_csv"
    assert data["meta"]["read_only"] is True
    assert data["meta"]["reduced_mode"] is False
    assert data["meta"]["campaign_mode"] == "equipment_first"
    assert data["meta"]["source_path"] == "equipment_first_operator_queue_20260518.csv"
    assert "/home/" not in data["meta"]["source_path"]
    assert data["meta"]["source_path_info"] == {
        "redacted": True,
        "basename": "equipment_first_operator_queue_20260518.csv",
        "kind": "file",
    }
    assert data["meta"]["count"] == 3
    assert data["items"][0]["priority_rank"] == 1
    assert data["items"][0]["codigo_licitacion"] == "LP-001"


def test_opportunities_equipment_reads_manifest_canonical_path(tmp_path: Path) -> None:
    client = _client(tmp_path)
    data = client.get("/opportunities/equipment?limit=1").json()
    assert data["items"][0]["buyer"] == "Buyer One"
    assert "crosscheck" not in data["meta"]["source_path"]


def test_opportunities_equipment_priority_filter(tmp_path: Path) -> None:
    client = _client(tmp_path)
    data = client.get("/opportunities/equipment?priority=2").json()
    assert data["meta"]["count"] == 1
    assert data["items"][0]["codigo_licitacion"] == "LP-002"


def test_opportunities_equipment_safe_channel_filter(tmp_path: Path) -> None:
    client = _client(tmp_path)
    data = client.get("/opportunities/equipment?safe_channel=mercado_publico_bid").json()
    assert all(i["safe_channel"] == "mercado_publico_bid" for i in data["items"])


def test_opportunities_equipment_exclude_account_intelligence(tmp_path: Path) -> None:
    client = _client(tmp_path)
    data = client.get("/opportunities/equipment?include_account_intelligence=false").json()
    assert data["meta"]["count"] == 2
    assert all(i["safe_channel"] != "account_intelligence_only" for i in data["items"])


def test_opportunities_equipment_missing_csv_reduced_mode(tmp_path: Path) -> None:
    client = _client(tmp_path, with_csv=False)
    r = client.get("/opportunities/equipment")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["reduced_mode"] is True
    assert data["items"] == []
    assert "not found" in data["meta"]["note"].lower()


def test_opportunities_equipment_validates_limit(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/opportunities/equipment?limit=0").status_code == 422
    assert client.get("/opportunities/equipment?limit=500").status_code == 422


def test_opportunities_equipment_no_extra_columns(tmp_path: Path) -> None:
    client = _client(tmp_path)
    item = client.get("/opportunities/equipment?limit=1").json()["items"][0]
    assert "supplier_contact" not in item
    assert "gmail_prior_thread" not in item
