"""Regression: warm cases API returns payment_admin and vendor_logistics rows."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import Settings

_CONTACTO_INBOX = "gmail:contacto@origenlab.cl/INBOX"


def _warm_client(tmp_path: Path, rows: list[tuple]) -> TestClient:
    db = tmp_path / "t.sqlite"
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
    for row in rows:
        conn.execute(
            "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
            row,
        )
    conn.commit()
    conn.close()
    app = create_app()
    from origenlab_api.settings import get_settings

    active = tmp_path / "current"
    active.mkdir(parents=True)
    (active / "manifest.json").write_text(
        json.dumps({"canonical_files": [], "campaign_mode": "equipment_first"}),
        encoding="utf-8",
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        sqlite_path=db,
        active_current=active,
    )
    return TestClient(app)


def test_warm_api_payment_admin_category_filter(tmp_path: Path) -> None:
    client = _warm_client(
        tmp_path,
        [
            (
                "2026-05-22T11:34:00-04:00",
                _CONTACTO_INBOX,
                "INBOX",
                "serviciodetransferencias@bancochile.cl",
                "FACTURA 6",
            ),
        ],
    )
    data = client.get(
        "/cases/warm?positive_signal_only=false&category=payment_admin&limit=50"
    ).json()
    assert len(data["items"]) == 1
    assert data["items"][0]["contact_email"] == "serviciodetransferencias@bancochile.cl"
    assert data["items"][0]["category"] == "payment_admin"


def test_warm_api_vendor_logistics_category_filter(tmp_path: Path) -> None:
    client = _warm_client(
        tmp_path,
        [
            (
                "2026-05-22T16:09:00-04:00",
                _CONTACTO_INBOX,
                "INBOX",
                "Monica Silva <monica.silva@dhl.com>",
                "RE: Solicitud cuenta importación",
            ),
        ],
    )
    data = client.get(
        "/cases/warm?positive_signal_only=false&category=vendor_logistics&limit=50"
    ).json()
    assert len(data["items"]) == 1
    assert data["items"][0]["contact_email"] == "monica.silva@dhl.com"
    assert data["items"][0]["category"] == "vendor_logistics"


def test_warm_api_default_excludes_internal_contacto(tmp_path: Path) -> None:
    client = _warm_client(
        tmp_path,
        [
            (
                "2026-05-22T10:00:00-04:00",
                _CONTACTO_INBOX,
                "INBOX",
                "contacto@origenlab.cl",
                "Re: Quotation Request",
            ),
            (
                "2026-05-22T11:34:00-04:00",
                _CONTACTO_INBOX,
                "INBOX",
                "serviciodetransferencias@bancochile.cl",
                "FACTURA 6",
            ),
        ],
    )
    data = client.get("/cases/warm?limit=50").json()
    emails = {i["contact_email"].lower() for i in data["items"]}
    assert "contacto@origenlab.cl" not in emails
    assert "serviciodetransferencias@bancochile.cl" in emails


