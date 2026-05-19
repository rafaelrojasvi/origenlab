"""GET /cases/warm — warm commercial case queue."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import Settings

_CONTACTO_SENT = "gmail:contacto@origenlab.cl/[Gmail]/Enviados"
_CONTACTO_INBOX = "gmail:contacto@origenlab.cl/INBOX"


def _client(tmp_path: Path, db: Path, *, seed: bool = True) -> TestClient:
    active = tmp_path / "current"
    active.mkdir(parents=True)
    (active / "manifest.json").write_text(
        json.dumps({"canonical_files": [], "campaign_mode": "equipment_first"}),
        encoding="utf-8",
    )
    if seed:
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE emails (
                id INTEGER PRIMARY KEY,
                date_iso TEXT,
                source_file TEXT,
                folder TEXT,
                sender TEXT,
                subject TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
            (
                "2026-05-19T10:00:00-04:00",
                _CONTACTO_INBOX,
                "INBOX",
                "Kelly Liu <kelly@supplier.com>",
                "Re: Ollital reactor 5L",
            ),
        )
        conn.execute(
            "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
            (
                "2026-05-19T09:00:00-04:00",
                _CONTACTO_SENT,
                "[Gmail]/Enviados",
                "contacto@origenlab.cl",
                "Cotización equipos",
            ),
        )
        conn.commit()
        conn.close()
    app = create_app()
    from origenlab_api.settings import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        sqlite_path=db,
        active_current=active,
    )
    return TestClient(app)


def test_cases_warm_returns_200(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    r = client.get("/cases/warm?positive_signal_only=false&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["data_source"] == "sqlite"
    assert data["meta"]["read_only"] is True
    assert data["meta"]["count"] >= 1
    assert len(data["items"]) >= 1


def test_cases_warm_no_body_fields(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    item = client.get("/cases/warm?positive_signal_only=false&limit=5").json()["items"][0]
    dumped = json.dumps(item)
    assert "body_preview" not in dumped
    assert '"body"' not in dumped
    assert item["gmail_url"] is None
    assert item["case_id"].startswith("gmail-contacto-")


def test_cases_warm_validates_category(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    r = client.get("/cases/warm?category=not_a_real_category")
    assert r.status_code == 422


def test_cases_warm_category_filter(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    r = client.get("/cases/warm?positive_signal_only=false&category=quote_sent")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["category"] == "quote_sent"


def test_cases_warm_positive_signal_only_without_ci_table(tmp_path: Path) -> None:
    db = tmp_path / "missing_ci.sqlite"
    client = _client(tmp_path, db)
    r = client.get("/cases/warm?positive_signal_only=true&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["reduced_mode"] is True
    assert data["items"] == []
    assert data["meta"]["count"] == 0


def test_cases_warm_missing_sqlite_graceful(tmp_path: Path) -> None:
    db = tmp_path / "nope.sqlite"
    client = _client(tmp_path, db, seed=False)
    r = client.get("/cases/warm")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["reduced_mode"] is True
    assert data["items"] == []


def test_cases_warm_query_param_bounds(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    assert client.get("/cases/warm?days=0").status_code == 422
    assert client.get("/cases/warm?limit=201").status_code == 422


def test_cases_warm_include_noise_shows_bounce(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
        (
            "2026-05-19T08:00:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "mailer-daemon@google.com",
            "Delivery Status Notification (Failure)",
        ),
    )
    conn.commit()
    conn.close()
    r = client.get("/cases/warm?include_noise=true&positive_signal_only=false&limit=20")
    assert r.status_code == 200
    categories = {i["category"] for i in r.json()["items"]}
    assert "bounce" in categories
