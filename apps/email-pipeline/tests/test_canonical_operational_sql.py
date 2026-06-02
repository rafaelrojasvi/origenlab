"""Tests for neutral canonical Gmail operational SQL (``canonical_operational_sql``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import origenlab_email_pipeline.canonical_operational_sql as canonical_sql
import origenlab_email_pipeline.streamlit_canonical_dashboard_sql as streamlit_shim
from origenlab_email_pipeline.canonical_operational_sql import (
    count_canonical_duplicate_message_id_groups,
    count_canonical_missing_message_id,
    direction_label_for_folder,
    load_canonical_gmail_classification_sample,
    load_inicio_recent_canonical_rows,
)


def test_shim_reexports_same_callables_as_canonical_module() -> None:
    for name in canonical_sql.__all__:
        assert getattr(streamlit_shim, name) is getattr(canonical_sql, name)


def _mk(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "x.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          date_iso TEXT,
          subject TEXT,
          sender TEXT,
          folder TEXT,
          message_id TEXT,
          body TEXT,
          full_body_clean TEXT,
          top_reply_clean TEXT,
          attachment_count INTEGER,
          source_file TEXT
        );
        CREATE TABLE attachments (id INTEGER PRIMARY KEY, email_id INTEGER NOT NULL);
        """
    )
    src = "gmail:contacto@origenlab.cl/INBOX"
    conn.executemany(
        "INSERT INTO emails (date_iso, subject, sender, folder, message_id, body, attachment_count, source_file) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-04-01T10:00:00Z", "Hi", "a@x.cl", "INBOX", "<a@1>", "x", 0, src),
            ("2026-04-02T10:00:00Z", "Hi", "a@x.cl", "INBOX", "<a@1>", "x", 0, src),
            ("2026-04-03T10:00:00Z", "Out", "b@y.cl", "[Gmail]/Enviados", "<b@1>", "y", 1, src),
        ],
    )
    conn.execute("INSERT INTO attachments (email_id) VALUES (3)")
    conn.commit()
    return conn


def test_count_duplicate_groups_and_missing_mid(tmp_path: Path) -> None:
    conn = _mk(tmp_path)
    try:
        assert count_canonical_duplicate_message_id_groups(conn) == 1
        assert count_canonical_missing_message_id(conn) == 0
    finally:
        conn.close()


def test_load_inicio_recent_respects_limit(tmp_path: Path) -> None:
    conn = _mk(tmp_path)
    try:
        rows = load_inicio_recent_canonical_rows(conn, limit=2)
        assert len(rows) == 2
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("folder", "label"),
    [
        ("[Gmail]/Enviados", "Enviado"),
        ("INBOX", "Recibido"),
    ],
)
def test_direction_label_for_folder(folder: str, label: str) -> None:
    assert direction_label_for_folder(folder) == label


def test_load_canonical_gmail_classification_sample_respects_window(tmp_path: Path) -> None:
    db_path = tmp_path / "cls.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          date_iso TEXT,
          subject TEXT,
          sender TEXT,
          recipients TEXT,
          folder TEXT,
          body TEXT,
          full_body_clean TEXT,
          top_reply_clean TEXT,
          source_file TEXT
        );
        """
    )
    src = "gmail:contacto@origenlab.cl/INBOX"
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=400)).strftime("%Y-%m-%dT10:00:00Z")
    new = (now - timedelta(days=5)).strftime("%Y-%m-%dT10:00:00Z")
    conn.executemany(
        "INSERT INTO emails (date_iso, subject, sender, recipients, folder, body, full_body_clean, top_reply_clean, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (old, "Old", "a@b.c", "contacto@origenlab.cl", "INBOX", "x", "", "", src),
            (new, "New", "c@d.e", "contacto@origenlab.cl", "INBOX", "y", "", "", src),
        ],
    )
    conn.commit()
    rows = load_canonical_gmail_classification_sample(conn, days=30, limit=50)
    assert len(rows) == 1
    assert rows[0]["subject"] == "New"
    conn.close()
