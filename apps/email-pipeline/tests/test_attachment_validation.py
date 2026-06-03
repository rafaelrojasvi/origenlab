"""Tests for attachment validation library and CLI."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from origenlab_email_pipeline.validation.attachment_validation import (
    SUMMARY_KEYS,
    format_attachment_validation_report,
    run_attachment_validation,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "validation" / "validate_attachments.py"


def _seed_consistent_db(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            has_attachments INTEGER,
            attachment_count INTEGER,
            subject TEXT,
            top_reply_clean TEXT
        );
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY,
            email_id INTEGER,
            filename TEXT,
            content_type TEXT,
            size_bytes INTEGER,
            is_inline INTEGER,
            sha256 TEXT
        );
        INSERT INTO emails (id, has_attachments, attachment_count, subject, top_reply_clean)
        VALUES (1, 1, 1, 'Cotización equipos', '');
        INSERT INTO attachments (id, email_id, filename, content_type, size_bytes, is_inline, sha256)
        VALUES (1, 1, 'quote.pdf', 'application/pdf', 1024, 0, 'abc123');
        """
    )
    conn.commit()
    conn.close()


def _seed_drift_db(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            has_attachments INTEGER,
            attachment_count INTEGER,
            subject TEXT,
            top_reply_clean TEXT
        );
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY,
            email_id INTEGER,
            filename TEXT,
            content_type TEXT,
            size_bytes INTEGER,
            is_inline INTEGER,
            sha256 TEXT
        );
        INSERT INTO emails (id, has_attachments, attachment_count, subject, top_reply_clean)
        VALUES (1, 1, 2, 'Missing rows', '');
        """
    )
    conn.commit()
    conn.close()


def test_summary_keys_locked() -> None:
    assert SUMMARY_KEYS == frozenset(
        {
            "total_emails",
            "total_attachments",
            "emails_with_attachments",
            "emails_non_inline",
            "emails_business_doc",
            "drift_has_attachments_no_rows",
            "drift_attachment_count_mismatch",
            "missing_filename_with_size",
            "zero_size_attachments",
            "duplicate_sha256_groups",
        }
    )


def test_run_attachment_validation_consistent_fixture(tmp_path: Path) -> None:
    db = tmp_path / "attachments.sqlite"
    _seed_consistent_db(db)
    conn = sqlite3.connect(db)
    try:
        result = run_attachment_validation(conn)
    finally:
        conn.close()

    assert set(result.summary) == SUMMARY_KEYS
    assert result.summary["total_emails"] == 1
    assert result.summary["total_attachments"] == 1
    assert result.summary["emails_with_attachments"] == 1
    assert result.summary["drift_has_attachments_no_rows"] == 0
    assert result.summary["drift_attachment_count_mismatch"] == 0
    assert result.class_pdf == 1
    assert result.cotiz_business == 1

    report = format_attachment_validation_report(result, db)
    assert "=== Attachments validation (Phase 2.3) ===" in report
    assert "Total emails: 1" in report
    assert "Total attachments: 1" in report
    assert report.endswith("\nDone.")


def test_run_attachment_validation_detects_drift(tmp_path: Path) -> None:
    db = tmp_path / "drift.sqlite"
    _seed_drift_db(db)
    conn = sqlite3.connect(db)
    try:
        result = run_attachment_validation(conn)
    finally:
        conn.close()

    assert result.summary["drift_has_attachments_no_rows"] == 1
    assert result.summary["drift_attachment_count_mismatch"] == 1


def test_cli_smoke_with_env_db(tmp_path: Path) -> None:
    db = tmp_path / "attachments.sqlite"
    _seed_consistent_db(db)
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "ORIGENLAB_SQLITE_PATH": str(db)}
    cp = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert cp.returncode == 0, cp.stderr + cp.stdout
    assert "=== Attachments validation (Phase 2.3) ===" in cp.stdout
    assert "Total attachments: 1" in cp.stdout
    assert cp.stdout.strip().endswith("Done.")


def test_cli_missing_db_exits_one(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "ORIGENLAB_SQLITE_PATH": str(missing)}
    cp = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert cp.returncode == 1
    assert "DB not found:" in cp.stderr


def test_script_docstring_available() -> None:
    """Script has no argparse flags; lock module docstring for operator discovery."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"""Validate attachment metadata (Phase 2.3)' in text
