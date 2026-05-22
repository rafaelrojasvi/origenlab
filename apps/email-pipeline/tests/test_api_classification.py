"""Tests for read-only /classification/* endpoints (mocked Postgres)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.config import reset_api_settings_cache
from origenlab_api.main import create_app
from test_api_slice1 import FakeConn, _FakeCursor


class ClassificationFakeConn(FakeConn):
    def __init__(self) -> None:
        super().__init__()
        self.tables[("reporting", "email_classification_canonical")] = True
        self.classification_rows: list[dict[str, Any]] = [
            {
                "email_id": 1,
                "date_iso": "2026-05-10T12:00:00",
                "folder": "INBOX",
                "from_addr": "buyer@lab.cl",
                "to_addrs": "contacto@origenlab.cl",
                "subject": "Solicitud de cotización",
                "predicted_label": "quote_request_inbound",
                "confidence": "high_confidence",
                "ambiguous": False,
                "recommended_action": "responder_solicitud",
                "etiqueta_ui": "Posible solicitud",
                "evidence": "quote_strong",
            },
            {
                "email_id": 2,
                "date_iso": "2026-05-09T10:00:00",
                "folder": "[Gmail]/Enviados",
                "from_addr": "contacto@origenlab.cl",
                "to_addrs": "buyer@lab.cl",
                "subject": "Cotización adjunta",
                "predicted_label": "cotizacion_sent",
                "confidence": "high_confidence",
                "ambiguous": False,
                "recommended_action": "revisar_cotizacion",
                "etiqueta_ui": "Posible cotización enviada",
                "evidence": "sent_keywords",
            },
            {
                "email_id": 3,
                "date_iso": "2026-05-08T09:00:00",
                "folder": "INBOX",
                "from_addr": "compras@empresa.cl",
                "to_addrs": "contacto@origenlab.cl",
                "subject": "Orden de compra 1234",
                "predicted_label": "purchase_or_order_signal",
                "confidence": "high_confidence",
                "ambiguous": False,
                "recommended_action": "revisar_cliente_activo",
                "etiqueta_ui": "Posible compra / orden",
                "evidence": "purchase_strong",
            },
        ]

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "from reporting.email_classification_canonical" in s:
            if "group by predicted_label" in s:
                counts: dict[str, int] = {}
                for row in self.classification_rows:
                    lbl = str(row["predicted_label"])
                    counts[lbl] = counts.get(lbl, 0) + 1
                return _FakeCursor(
                    [{"predicted_label": k, "n": v} for k, v in sorted(counts.items())]
                )
            if "group by recommended_action" in s:
                counts_a: dict[str, int] = {}
                for row in self.classification_rows:
                    act = str(row["recommended_action"])
                    counts_a[act] = counts_a.get(act, 0) + 1
                return _FakeCursor(
                    [
                        {"recommended_action": k, "n": v}
                        for k, v in sorted(counts_a.items(), key=lambda x: -x[1])
                    ]
                )
            if "count(*)" in s:
                label = None
                if params and len(params) >= 1 and "predicted_label" in s:
                    label = params[0]
                rows = self.classification_rows
                if label:
                    rows = [r for r in rows if r["predicted_label"] == label]
                return _FakeCursor([{"n": len(rows)}])
            if "select subject" in s and params:
                action = params[0]
                subs = [
                    {"subject": r["subject"]}
                    for r in self.classification_rows
                    if r["recommended_action"] == action
                ][:3]
                return _FakeCursor(subs)
            if "select email_id" in s:
                label = None
                if params and "predicted_label" in s:
                    label = params[0]
                rows = list(self.classification_rows)
                if label:
                    rows = [r for r in rows if r["predicted_label"] == label]
                lim = params[-1] if params else len(rows)
                return _FakeCursor(rows[: int(lim)])
        return super().execute(sql, params)


@pytest.fixture
def class_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Generator[TestClient, None, None]:
    reset_api_settings_cache()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    fake = ClassificationFakeConn()

    @contextmanager
    def _fake_pg(_url: str) -> Generator[ClassificationFakeConn, None, None]:
        yield fake

    monkeypatch.setattr("origenlab_api.deps.postgres_connection", _fake_pg)
    monkeypatch.setattr("origenlab_api.db.postgres_connection", _fake_pg)
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.db.postgres_connection",
        _fake_pg,
    )
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        _fake_pg,
    )
    app = create_app()
    with TestClient(app) as tc:
        yield tc
    reset_api_settings_cache()


def test_classification_summary_canonical_only(class_client: TestClient) -> None:
    r = class_client.get("/classification/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["table_available"] is True
    assert body["status"] == "ok"
    assert body["kpi"]["posibles_solicitudes"] == 1
    assert body["kpi"]["cotizaciones_enviadas"] == 1
    assert body["kpi"]["posibles_compras"] == 1


def test_classification_recent_filter(class_client: TestClient) -> None:
    r = class_client.get(
        "/classification/recent",
        params={"label": "purchase_or_order_signal", "limit": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert len(body["items"]) == 1
    assert body["items"][0]["predicted_label"] == "purchase_or_order_signal"
    assert body["items"][0]["recommended_action"] == "revisar_cliente_activo"


def test_classification_actions(class_client: TestClient) -> None:
    r = class_client.get("/classification/actions")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert len(body["groups"]) >= 2


def test_classification_missing_table(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    reset_api_settings_cache()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))
    fake = FakeConn()
    fake.tables[("reporting", "email_classification_canonical")] = False

    @contextmanager
    def _fake_pg(_url: str) -> Generator[FakeConn, None, None]:
        yield fake

    monkeypatch.setattr("origenlab_api.deps.postgres_connection", _fake_pg)
    monkeypatch.setattr("origenlab_api.db.postgres_connection", _fake_pg)
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.db.postgres_connection",
        _fake_pg,
    )
    with TestClient(create_app()) as client:
        r = client.get("/classification/summary")
    assert r.json()["table_available"] is False
    assert r.json()["status"] == "missing_table"
