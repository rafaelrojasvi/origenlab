"""Minimal Gmail Sent rows so :func:`probe_sent_history` passes in archive/CLI tests."""

from __future__ import annotations

import sqlite3

DEFAULT_TEST_GMAIL_USER = "contacto@origenlab.cl"
DEFAULT_TEST_SENT_FOLDER = "[Gmail]/Enviados"


def seed_minimal_sent_history_for_preflight(
    conn: sqlite3.Connection,
    *,
    gmail_user: str = DEFAULT_TEST_GMAIL_USER,
    folder: str = DEFAULT_TEST_SENT_FOLDER,
) -> None:
    """One row matching ``gmail:{user}/%`` + Sent folder; parseable ``recipients``."""
    conn.execute(
        """
        INSERT INTO emails (recipients, source_file, folder)
        VALUES (?, ?, ?)
        """,
        (
            "sent-preflight-test@cliente.cl",
            f"gmail:{gmail_user}/pytest-sent-preflight.sqlite",
            folder,
        ),
    )


def seed_minimal_sent_history_for_preflight_extended_emails(
    conn: sqlite3.Connection,
    *,
    gmail_user: str = DEFAULT_TEST_GMAIL_USER,
    folder: str = DEFAULT_TEST_SENT_FOLDER,
) -> None:
    """Same semantics as :func:`seed_minimal_sent_history_for_preflight` for wider ``emails`` DDL."""
    conn.execute(
        """
        INSERT INTO emails (recipients, source_file, folder, sender, date_iso, date_raw)
        VALUES (?, ?, ?, '', '', '')
        """,
        (
            "sent-preflight-test@cliente.cl",
            f"gmail:{gmail_user}/pytest-sent-preflight.sqlite",
            folder,
        ),
    )
