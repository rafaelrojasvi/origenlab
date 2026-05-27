"""Tests for dashboard API production smoke (mocked HTTP)."""

from __future__ import annotations

from typing import Any

from origenlab_email_pipeline.qa.dashboard_api_readiness import (
    BLUESLICK_PRODUCT_KEY,
    TEMED_PRODUCT_KEY,
    collect_json_keys,
    run_dashboard_api_smoke,
    scan_payload_safety,
)


def _blueslick_history() -> list[dict[str, Any]]:
    return [
        {
            "line_side": "client",
            "line_kind": "product",
            "currency": "CLP",
            "amount_net_clp": 695000,
            "amount_decimal": None,
            "deal_label": "CEAF × SERVA",
        },
        {
            "line_side": "supplier",
            "line_kind": "product",
            "currency": "EUR",
            "amount_net_clp": None,
            "amount_decimal": "117.00",
            "deal_label": "CEAF × SERVA",
        },
    ]


def _temed_history() -> list[dict[str, Any]]:
    return [
        {
            "line_side": "client",
            "line_kind": "product",
            "currency": "CLP",
            "amount_net_clp": 545000,
            "amount_decimal": None,
        },
        {
            "line_side": "supplier",
            "line_kind": "product",
            "currency": "EUR",
            "amount_decimal": "31.00",
        },
    ]


def _good_responses() -> dict[str, dict[str, Any]]:
    return {
        "/health": {"ok": True, "service": "origenlab-api", "mode": "operator-postgres-readonly", "backend": "postgres"},
        "/operator/status": {
            "verdict": "READY",
            "campaign_mode": "equipment_first",
            "outbound_readiness": "ready",
            "warnings": [],
        },
        "/mirror/commercial/deals": {
            "table_available": True,
            "read_only": True,
            "data_source": "postgres_mirror",
            "total": 1,
            "items": [{"client_org_name": "CEAF", "supplier_org_name": "SERVA"}],
        },
        "/mirror/catalog/products": {
            "table_available": True,
            "read_only": True,
            "data_source": "postgres_mirror",
            "total": 9,
            "items": [{"product_key": "x", "display_name": "Product"}],
        },
        f"/mirror/catalog/products/{BLUESLICK_PRODUCT_KEY}": {
            "table_available": True,
            "read_only": True,
            "data_source": "postgres_mirror",
            "product": {
                "product_key": BLUESLICK_PRODUCT_KEY,
                "display_name": "BlueSlick™ 250 ml",
                "public_summary": "Vendido en electroforesis con cotización y disponibilidad.",
                "commercial_history": _blueslick_history(),
            },
        },
        f"/mirror/catalog/products/{TEMED_PRODUCT_KEY}": {
            "table_available": True,
            "read_only": True,
            "data_source": "postgres_mirror",
            "product": {
                "product_key": TEMED_PRODUCT_KEY,
                "display_name": "TEMED 25 ml",
                "commercial_history": _temed_history(),
            },
        },
        "/cases/warm": {
            "meta": {
                "data_source": "postgres_mirror",
                "read_only": True,
                "reduced_mode": False,
                "count": 3,
            },
            "items": [
                {
                    "case_id": "gmail-contacto-1",
                    "category": "client_opportunity",
                    "gmail_url": None,
                }
            ],
        },
        "/opportunities/equipment": {
            "meta": {
                "data_source": "postgres_mirror",
                "read_only": True,
                "reduced_mode": False,
                "count": 0,
                "source_path": "",
                "note": "",
            },
            "items": [],
        },
    }


def _mock_fetch(responses: dict[str, dict[str, Any]]):
    def fetch(path: str, params: dict[str, str | int]) -> tuple[int, dict[str, Any] | None, str]:
        _ = params
        body = responses.get(path)
        if body is None:
            return 404, None, "not found"
        return 200, body, ""

    return fetch


def test_scan_payload_safety_ignores_null_gmail_url() -> None:
    assert scan_payload_safety({"gmail_url": None}) == []


def test_scan_payload_safety_flags_forbidden_key_and_prose() -> None:
    errors = scan_payload_safety({"gmail_url": "https://mail.google.com/x"})
    assert any("forbidden keys" in e for e in errors)

    errors = scan_payload_safety({"snippet": "texto con montoes en resumen"})
    assert any("prose artifact" in e for e in errors)

    errors = scan_payload_safety({"note": "oportunida de s en catálogo"})
    assert any("prose artifact" in e for e in errors)


def test_smoke_passes_with_good_mock_responses() -> None:
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(_good_responses()),
    )
    assert report.passed
    assert len(report.checks) == 8
    assert "PASS" in report.summary_lines()[-1]


def test_smoke_fails_when_catalog_total_below_minimum() -> None:
    responses = _good_responses()
    responses["/mirror/catalog/products"]["total"] = 3
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(responses),
    )
    assert not report.passed
    catalog = next(c for c in report.checks if c.name.endswith("/products"))
    assert not catalog.ok
    assert "total=3" in catalog.detail


def test_smoke_fails_when_blueslick_history_missing_amounts() -> None:
    responses = _good_responses()
    responses[f"/mirror/catalog/products/{BLUESLICK_PRODUCT_KEY}"]["product"][
        "commercial_history"
    ] = []
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(responses),
    )
    assert not report.passed
    blueslick = next(c for c in report.checks if BLUESLICK_PRODUCT_KEY in c.name)
    assert not blueslick.ok


def test_smoke_fails_when_operator_exposes_sqlite_path() -> None:
    responses = _good_responses()
    responses["/operator/status"]["sqlite_path"] = "/home/user/secret/emails.sqlite"
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(responses),
    )
    assert not report.passed
    op = next(c for c in report.checks if "/operator/status" in c.name)
    assert "sqlite_path" in op.detail


def test_smoke_fails_on_forbidden_transfer_id_in_deals() -> None:
    responses = _good_responses()
    responses["/mirror/commercial/deals"]["items"][0]["transfer_id"] = "secret-transfer"
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(responses),
    )
    assert not report.passed
    keys: set[str] = set()
    collect_json_keys(responses["/mirror/commercial/deals"], keys)
    assert "transfer_id" in keys


def test_smoke_fails_when_equipment_exposes_source_path() -> None:
    responses = _good_responses()
    responses["/opportunities/equipment"]["meta"]["source_path"] = "/reports/out/secret.csv"
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(responses),
    )
    assert not report.passed
    eq = next(c for c in report.checks if "/opportunities/equipment" in c.name)
    assert "source_path" in eq.detail


def test_summary_does_not_embed_response_bodies() -> None:
    report = run_dashboard_api_smoke(
        "https://api.example.test",
        fetch=_mock_fetch(_good_responses()),
    )
    joined = "\n".join(report.summary_lines())
    assert "695000" not in joined
    assert "117.00" not in joined
    assert "postgresql://" not in joined
