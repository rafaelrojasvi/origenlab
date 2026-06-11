"""Tests for read-only Gmail interaction audit snapshot builder."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_PREFIX
from origenlab_email_pipeline.dashboard_gmail_interaction_audit import (
    build_gmail_interaction_audit_snapshot,
    canonical_audit_domain,
    find_audit_domain_row,
)
from origenlab_email_pipeline.db import init_schema

_NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
_CONTACTO = "contacto@origenlab.cl"
_IKA = "sales@ika.net.br"


def _insert_email(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    folder: str,
    sender: str,
    recipients: str,
    subject: str,
    date_iso: str,
    body: str = "secret body must not appear",
    has_attachments: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO emails (
          source_file, message_id, date_iso, folder, sender, recipients,
          subject, body, has_attachments
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{CONTACTO_GMAIL_SOURCE_PREFIX}{folder}/msg",
            message_id,
            date_iso,
            folder,
            sender,
            recipients,
            subject,
            body,
            has_attachments,
        ),
    )


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "audit.sqlite"
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    _insert_email(
        conn,
        message_id="in-1",
        folder="INBOX",
        sender=_IKA,
        recipients=_CONTACTO,
        subject="CONSULTA POR MOLINO",
        date_iso="2026-06-01T10:00:00",
        has_attachments=1,
    )
    _insert_email(
        conn,
        message_id="out-1",
        folder="[Gmail]/Enviados",
        sender=_CONTACTO,
        recipients=_IKA,
        subject="Re: CONSULTA POR MOLINO",
        date_iso="2026-06-02T10:00:00",
    )
    _insert_email(
        conn,
        message_id="in-2",
        folder="INBOX",
        sender=_IKA,
        recipients=_CONTACTO,
        subject="Re: CONSULTA POR MOLINO",
        date_iso="2026-06-03T10:00:00",
    )
    _insert_email(
        conn,
        message_id="internal-1",
        folder="INBOX",
        sender="ops@origenlab.cl",
        recipients="contacto@origenlab.cl",
        subject="Internal only",
        date_iso="2026-06-04T10:00:00",
    )
    conn.commit()
    conn.close()
    return db_path


def test_counts_sent_received_by_domain(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    row = find_audit_domain_row(snapshot, domain="ika.net.br")
    assert row is not None
    assert row["message_count"] == 3
    assert row["sent_count"] == 1
    assert row["received_count"] == 2


def test_groups_same_subject_thread(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    row = find_audit_domain_row(snapshot, domain="ika.net.br")
    assert row is not None
    assert row["thread_count"] == 1


def test_subject_fallback_when_no_thread_id(tmp_path: Path) -> None:
    db_path = tmp_path / "threads.sqlite"
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    for idx, subj in enumerate(("Topic A", "Re: Topic A", "Topic B"), start=1):
        _insert_email(
            conn,
            message_id=f"m-{idx}",
            folder="INBOX",
            sender="buyer@serva.de",
            recipients=_CONTACTO,
            subject=subj,
            date_iso=f"2026-06-0{idx}T10:00:00",
        )
    conn.commit()
    conn.close()
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    row = find_audit_domain_row(snapshot, domain="serva.de")
    assert row is not None
    assert row["thread_count"] == 2


def test_excludes_internal_domains(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    domains = {row["domain"] for row in snapshot["domains"]}
    assert "origenlab.cl" not in domains
    assert "labdelivery.cl" not in domains


def test_does_not_include_body_text(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    dumped = str(snapshot)
    assert "secret body must not appear" not in dumped


def test_latest_safe_subject_is_subject_only(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    row = find_audit_domain_row(snapshot, domain="ika.net.br")
    assert row is not None
    assert row["latest_subject_safe"] == "Re: CONSULTA POR MOLINO"
    assert "secret" not in row["latest_subject_safe"]


def test_handles_empty_sqlite_table(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    conn.close()
    snapshot = build_gmail_interaction_audit_snapshot(db_path, now=_NOW)
    assert snapshot["domains"] == []


def test_domain_alias_canonicalization() -> None:
    assert canonical_audit_domain("ika.com") == "ika.net.br"
    assert canonical_audit_domain("serva-electrophoresis.com") == "serva.de"
