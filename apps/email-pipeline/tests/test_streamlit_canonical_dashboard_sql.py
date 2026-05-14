"""Tests for read-only canonical Gmail dashboard SQL helpers (Streamlit KPIs)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.streamlit_canonical_dashboard_sql import (
    count_canonical_duplicate_message_id_groups,
    count_canonical_missing_message_id,
    direction_label_for_folder,
    load_inicio_recent_canonical_rows,
)


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
