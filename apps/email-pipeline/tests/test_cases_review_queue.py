from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.cases_review_queue import (
    CONTACTO_GMAIL_SOURCE_SQL,
    commercial_hint_es,
    fetch_case_detail,
    fetch_cases_review_queue,
    looks_like_obvious_noise,
)


def _mk_emails(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          date_iso TEXT,
          subject TEXT,
          sender TEXT,
          source_file TEXT,
          message_id TEXT,
          top_reply_clean TEXT,
          full_body_clean TEXT,
          body_text_clean TEXT,
          body TEXT
        );
        """
    )


def test_contacto_gmail_filter_in_sql_constant() -> None:
    assert "gmail:contacto@origenlab.cl" in CONTACTO_GMAIL_SOURCE_SQL


def test_fetch_queue_reduced_mode_without_cisf(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    _mk_emails(conn)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(1, '2026-03-20', 'Hola', 'a@ext.com', 'gmail:contacto@origenlab.cl/inbox'), "
        "(2, '2026-03-10', 'Otro', 'b@ext.com', 'imap:contacto@origenlab.cl/inbox')"
    )
    conn.commit()
    r = fetch_cases_review_queue(conn, days_window=90, exclude_obvious_noise=False, limit=50)
    conn.close()
    assert r.reduced_mode is True
    assert len(r.rows) == 1
    assert r.rows[0]["email_id"] == 1


def test_fetch_queue_with_enrichment(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    _mk_emails(conn)
    conn.executescript(
        """
        CREATE TABLE commercial_email_signal_fact (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email_id INTEGER NOT NULL,
          source_file TEXT NOT NULL,
          sent_at TEXT,
          sender_email TEXT,
          sender_domain TEXT,
          contact_email TEXT,
          contact_domain TEXT,
          org_domain TEXT,
          signal_code TEXT NOT NULL,
          signal_kind TEXT NOT NULL,
          reason_code TEXT NOT NULL,
          reason_text TEXT NOT NULL,
          confidence_score REAL NOT NULL,
          strength_score REAL NOT NULL,
          rationale_json TEXT NOT NULL,
          run_id INTEGER,
          created_at TEXT NOT NULL,
          UNIQUE(email_id, signal_code, reason_code, contact_email, org_domain)
        );
        """
    )
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(10, '2026-03-25', 'Cotización', 'c@x.cl', 'gmail:contacto@origenlab.cl/inbox')"
    )
    conn.execute(
        """INSERT INTO commercial_email_signal_fact (
          email_id, source_file, signal_code, signal_kind, reason_code, reason_text,
          confidence_score, strength_score, rationale_json, created_at
        ) VALUES (10, 'x', 'q', 'positive', 'r', 't', 0.8, 0.7, '{}', '2026-03-25T00:00:00Z')"""
    )
    conn.commit()
    r = fetch_cases_review_queue(conn, days_window=90, exclude_obvious_noise=False, limit=50)
    assert r.enrichment_available is True
    assert r.rows[0]["has_positive_signal"] == 1
    assert r.rows[0]["max_positive_strength"] == pytest.approx(0.7)
    hint = commercial_hint_es(r.rows[0], enrichment_available=True)
    assert "Señal comercial" in hint
    conn.close()


def test_positive_only_requires_cisf(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    _mk_emails(conn)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(1, '2026-03-20', 'X', 'a@b.c', 'gmail:contacto@origenlab.cl/x')"
    )
    conn.commit()
    r = fetch_cases_review_queue(
        conn, days_window=90, positive_signal_only=True, exclude_obvious_noise=False, limit=50
    )
    conn.close()
    assert r.rows == []


def test_noise_exclusion(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    _mk_emails(conn)
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file) VALUES "
        "(1, '2026-03-20', 'ok', 'human@x.cl', 'gmail:contacto@origenlab.cl/x'), "
        "(2, '2026-03-21', 'Delivery Status', 'mailer-daemon@x', 'gmail:contacto@origenlab.cl/x')"
    )
    conn.commit()
    r = fetch_cases_review_queue(conn, days_window=90, exclude_obvious_noise=True, limit=50)
    conn.close()
    ids = {row["email_id"] for row in r.rows}
    assert 1 in ids
    assert 2 not in ids


def test_looks_like_obvious_noise() -> None:
    assert looks_like_obvious_noise("MAILER-DAEMON@x", "hi") is True
    assert looks_like_obvious_noise("human@x.cl", "Delivery Status Failure") is True
    assert looks_like_obvious_noise("human@x.cl", "Cotización balanza") is False


def test_fetch_case_detail_document_count(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    _mk_emails(conn)
    conn.execute(
        """CREATE TABLE document_master (
          id INTEGER PRIMARY KEY,
          email_id INTEGER,
          sender_domain TEXT,
          recipient_domain TEXT,
          doc_type TEXT,
          sent_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO emails (id, date_iso, subject, sender, source_file, top_reply_clean) VALUES "
        "(5, '2026-01-01', 'S', 'a@b', 'gmail:contacto@origenlab.cl/x', 'cuerpo')"
    )
    conn.execute("INSERT INTO document_master (id, email_id, sender_domain) VALUES (1, 5, 'x.cl')")
    conn.commit()
    d = fetch_case_detail(conn, email_id=5)
    conn.close()
    assert d is not None
    assert d["document_count"] == 1
    assert "cuerpo" in (d.get("body_preview") or "")
