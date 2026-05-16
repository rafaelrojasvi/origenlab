"""Tests for classification Postgres mirror builder (SQLite read-only)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.classification_postgres_mirror import build_classification_rows
from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_PREFIX


def _insert_email(
    conn: sqlite3.Connection,
    *,
    email_id: int,
    subject: str,
    sender: str,
    folder: str = "INBOX",
) -> None:
    conn.execute(
        """
        INSERT INTO emails (
          id, source_file, date_iso, folder, sender, recipients, subject, body
        ) VALUES (?, ?, '2026-05-10', ?, ?, 'contacto@origenlab.cl', ?, ?)
        """,
        (
            email_id,
            f"{CONTACTO_GMAIL_SOURCE_PREFIX}{folder}/msg",
            folder,
            sender,
            subject,
            subject,
        ),
    )


def test_build_classification_rows_canonical_only(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          source_file TEXT,
          date_iso TEXT,
          folder TEXT,
          sender TEXT,
          recipients TEXT,
          subject TEXT,
          body TEXT,
          full_body_clean TEXT,
          top_reply_clean TEXT
        )
        """
    )
    _insert_email(
        conn,
        email_id=1,
        subject="Solicitud de cotización para equipos",
        sender="cliente@lab.cl",
    )
    _insert_email(
        conn,
        email_id=2,
        subject="Orden de compra 55",
        sender="compras@empresa.cl",
    )
    conn.commit()
    conn.close()

    rows = build_classification_rows(db, days=30, limit=50)
    assert len(rows) == 2
    labels = {r["predicted_label"] for r in rows}
    assert "quote_request_inbound" in labels or "purchase_or_order_signal" in labels
    assert all(r["source_scope"] == "canonical" for r in rows)
