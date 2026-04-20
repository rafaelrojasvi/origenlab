"""Tests for scripts/qa/validate_sqlite_archive_for_postgres.py (read-only archive validation)."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.db import init_schema

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "validate_sqlite_archive_for_postgres.py"


def _load_validation_module():
    spec = importlib.util.spec_from_file_location("validate_sqlite_archive_for_postgres", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v = _load_validation_module()


def _writable_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def _minimal_archive(path: Path) -> None:
    conn = _writable_db(path)
    init_schema(conn)
    conn.execute("DELETE FROM attachment_extracts")
    conn.execute("DELETE FROM attachments")
    conn.execute("DELETE FROM document_master")
    conn.execute("DELETE FROM emails")
    conn.executemany(
        """
        INSERT INTO emails
        (source_file, folder, message_id, date_iso, body_has_plain, body_has_html, has_attachments)
        VALUES (?, ?, ?, ?, 1, 0, 0)
        """,
        [
            ("mbox:/a", "Inbox", "m1", "2024-01-15T12:00:00+00:00"),
            (
                "gmail:user@gmail.com",
                "[Gmail]/Enviados",
                "m2",
                "2024-02-01T00:00:00Z",
            ),
        ],
    )
    conn.execute(
        """
        INSERT INTO attachments
        (email_id, part_index, filename, is_inline, created_at)
        VALUES (1, 0, 'a.pdf', 0, '2024-01-15T12:00:01+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO attachment_extracts
        (attachment_id, extract_status, extract_method, has_quote_terms, has_invoice_terms,
         has_price_list_terms, has_purchase_terms, created_at)
        VALUES (1, 'ok', 'pdf', 0, 0, 0, 0, '2024-01-15T12:00:02+00:00')
        """
    )
    conn.commit()
    conn.close()


def test_parse_iso_timestamp_accepts_z_and_offset() -> None:
    assert v.parse_iso_timestamp("2024-01-01T00:00:00Z")
    assert v.parse_iso_timestamp("2024-01-01T00:00:00+00:00")
    assert not v.parse_iso_timestamp("not-a-date")
    assert not v.parse_iso_timestamp("")
    assert not v.parse_iso_timestamp(None)


def test_is_bool01() -> None:
    assert v.is_bool01(None)
    assert v.is_bool01(0)
    assert v.is_bool01(1)
    assert not v.is_bool01(2)
    assert not v.is_bool01(True)


def test_build_report_clean_db(tmp_path: Path) -> None:
    db = tmp_path / "ok.sqlite"
    _minimal_archive(db)
    conn = v._connect_readonly(db)
    try:
        r = v.build_report(conn, sample_limit=5)
    finally:
        conn.close()
    assert r["ok"] is True
    assert r["counts"]["emails"] == 2
    assert r["counts"]["attachments"] == 1
    assert r["counts"]["attachment_extracts"] == 1
    assert r["counts"]["document_master"] == 0
    assert r["quality_checks"]["emails_null_or_empty_source_file"] == 0
    assert r["quality_checks"]["gmail_sent_rows"] == 1
    assert "[Gmail]/Enviados" in r["quality_checks"]["gmail_source_file_distinct_folders"]


def test_strict_flags_invalid_timestamp(tmp_path: Path) -> None:
    db = tmp_path / "bad_ts.sqlite"
    _minimal_archive(db)
    w = _writable_db(db)
    w.execute("UPDATE emails SET date_iso = 'bogus' WHERE id = 1")
    w.commit()
    w.close()
    conn = v._connect_readonly(db)
    try:
        r = v.build_report(conn, sample_limit=3)
    finally:
        conn.close()
    assert r["ok"] is False
    assert r["timestamp_checks"]["emails.date_iso"]["invalid"] >= 1


def test_strict_flags_orphan_attachment(tmp_path: Path) -> None:
    db = tmp_path / "orphan.sqlite"
    _minimal_archive(db)
    w = _writable_db(db)
    w.execute(
        """
        INSERT INTO attachments (email_id, part_index, filename, is_inline, created_at)
        VALUES (9999, 0, 'orph.pdf', 0, '2024-01-01T00:00:00+00:00')
        """
    )
    w.commit()
    w.close()
    conn = v._connect_readonly(db)
    try:
        r = v.build_report(conn, sample_limit=5)
    finally:
        conn.close()
    assert r["ok"] is False
    assert r["orphan_checks"]["attachments_missing_email"]["count"] == 1


def test_strict_flags_bad_boolean(tmp_path: Path) -> None:
    db = tmp_path / "bad_bool.sqlite"
    _minimal_archive(db)
    w = _writable_db(db)
    w.execute("UPDATE emails SET body_has_plain = 2 WHERE id = 1")
    w.commit()
    w.close()
    conn = v._connect_readonly(db)
    try:
        r = v.build_report(conn, sample_limit=5)
    finally:
        conn.close()
    assert r["ok"] is False
    assert r["boolean_checks"]["emails.body_has_plain"]["invalid"] >= 1


def test_strict_flags_empty_source_file(tmp_path: Path) -> None:
    db = tmp_path / "nosrc.sqlite"
    _minimal_archive(db)
    w = _writable_db(db)
    w.execute("UPDATE emails SET source_file = '' WHERE id = 1")
    w.commit()
    w.close()
    conn = v._connect_readonly(db)
    try:
        r = v.build_report(conn, sample_limit=5)
    finally:
        conn.close()
    assert r["ok"] is False
    assert r["quality_checks"]["emails_null_or_empty_source_file"] >= 1


def test_cli_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "cli.sqlite"
    _minimal_archive(db)
    monkeypatch.delenv("ORIGENLAB_SQLITE_PATH", raising=False)

    r0 = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db)],
        cwd=str(REPO),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r0.returncode == 0

    r1 = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--strict"],
        cwd=str(REPO),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0

    w = _writable_db(db)
    w.execute("UPDATE emails SET date_iso = 'bad'")
    w.commit()
    w.close()
    r2 = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--strict"],
        cwd=str(REPO),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 1

    out_json = tmp_path / "out.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--json-out", str(out_json)],
        cwd=str(REPO),
        check=True,
        capture_output=True,
        text=True,
    )
    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert "ok" in doc
    assert "counts" in doc
    assert "timestamp_checks" in doc
    assert "boolean_checks" in doc
    assert "orphan_checks" in doc
    assert "quality_checks" in doc
    assert "samples" in doc
    assert "duplicate_message_ids" in doc["samples"]


def test_resolve_db_path_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "fromenv.sqlite"
    p.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(p))
    assert v.resolve_db_path(None) == p.resolve()


def test_missing_db_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_SQLITE_PATH", raising=False)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(tmp_path / "nope.sqlite")],
        cwd=str(REPO),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
