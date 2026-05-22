"""GET /emails/recent — read-only canonical mail previews."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.settings import Settings

_CONTACTO_SENT = "gmail:contacto@origenlab.cl/[Gmail]/Enviados"


def _client(tmp_path: Path, db: Path, *, with_emails: bool = True) -> TestClient:
    active = tmp_path / "current"
    active.mkdir(parents=True)
    (active / "manifest.json").write_text(
        json.dumps(
            {
                "canonical_files": [],
                "campaign_mode": "equipment_first",
                "current_operator_focus": "test",
            }
        ),
        encoding="utf-8",
    )
    if with_emails:
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
                _CONTACTO_SENT,
                "[Gmail]/Enviados",
                "client@example.cl",
                "Cotización equipo",
            ),
        )
        conn.execute(
            "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
            (
                "2026-05-19T11:00:00-04:00",
                "other:mailbox@elsewhere/INBOX",
                "INBOX",
                "mailer-daemon@google.com",
                "Delivery Status Notification",
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


def test_emails_recent_empty_when_no_table(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    client = _client(tmp_path, db, with_emails=False)
    r = client.get("/emails/recent")
    assert r.status_code == 200
    data = r.json()
    assert data["total_returned"] == 0
    assert data["items"] == []
    assert data["meta"]["read_only"] is True
    assert data["meta"]["data_source"] == "sqlite"


def test_emails_recent_returns_canonical_contacto_only(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    r = client.get("/emails/recent?days=30&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total_returned"] == 1
    row = data["items"][0]
    assert row["email_id"] == 1
    assert "Cotización" in row["subject_preview"]
    assert data["meta"]["data_source"] == "sqlite"
    assert "contacto" in data["scope_note"].lower() or "source_file" in data["scope_note"]


def test_emails_recent_respects_limit(tmp_path: Path) -> None:
    """API ``limit`` caps rows after canonical contacto + days_window filters."""
    db = tmp_path / "many.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, source_file TEXT, folder TEXT, sender TEXT, subject TEXT)"
    )
    # Dates must fall inside default days=7 (prefix compare on date_iso); fixed May 10–14 goes stale.
    today = date.today()
    for i in range(5):
        day = today - timedelta(days=i)
        conn.execute(
            "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
            (
                f"{day.isoformat()}T12:00:00-04:00",
                _CONTACTO_SENT,
                "[Gmail]/Enviados",
                f"u{i}@x.cl",
                f"subj {i}",
            ),
        )
    conn.commit()
    conn.close()
    client = _client(tmp_path, db, with_emails=False)
    r = client.get("/emails/recent?limit=2")
    assert r.status_code == 200
    data = r.json()
    assert data["total_returned"] == 2
    assert len(data["items"]) == 2


def test_emails_recent_no_body_fields(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    client = _client(tmp_path, db)
    row = client.get("/emails/recent").json()["items"][0]
    assert "body" not in row
    assert "body_preview" not in row


def test_emails_recent_missing_db_returns_empty_items(tmp_path: Path) -> None:
    db = tmp_path / "missing.sqlite"
    client = _client(tmp_path, db, with_emails=False)
    r = client.get("/emails/recent")
    assert r.status_code == 200
    assert r.json()["total_returned"] == 0
