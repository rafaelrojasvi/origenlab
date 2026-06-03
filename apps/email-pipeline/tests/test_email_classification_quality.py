"""Tests for email classification quality audit library and CLI."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from origenlab_email_pipeline.qa.email_classification_quality import (
    REVIEW_CSV_FIELDS,
    SUMMARY_KEYS,
    attach_audit_meta,
    connect_readonly,
    run_audit,
    write_review_csv,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "audit_email_classification_quality.py"
CANON = "gmail:contacto@origenlab.cl/INBOX"


def _seed_db(db: Path) -> None:
    now = datetime.now(timezone.utc)
    day_iso = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT NOT NULL,
            folder TEXT,
            sender TEXT,
            recipients TEXT,
            subject TEXT,
            date_iso TEXT,
            body TEXT,
            full_body_clean TEXT,
            top_reply_clean TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            1,
            CANON,
            "INBOX",
            "buyer@cliente-test.cl",
            "contacto@origenlab.cl",
            "RFQ centrifuge",
            day_iso,
            "Please send us a quote for two units.",
            "",
            "",
        ),
    )
    conn.commit()
    conn.close()


def test_review_csv_columns_locked() -> None:
    assert REVIEW_CSV_FIELDS == (
        "email_id",
        "date_iso",
        "folder",
        "from_addr",
        "to_addrs",
        "subject",
        "predicted_label",
        "confidence",
        "ambiguous",
        "recommended_action",
        "etiqueta_ui",
        "evidence",
        "manual_label",
        "notes",
    )


def test_summary_keys_locked() -> None:
    assert SUMMARY_KEYS == frozenset(
        {
            "rows_scanned",
            "counts_by_primary",
            "ambiguous_rows",
            "likely_missed_quote_request",
            "supplier_domains_loaded",
            "internal_domains_used",
            "legacy_flag",
            "legacy_note",
        }
    )


def test_run_audit_library_fixture(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    _seed_db(db)
    conn = connect_readonly(db)
    try:
        payload = run_audit(conn, days=800, limit=100, legacy_also=False)
    finally:
        conn.close()

    summary = payload["summary"]
    assert set(summary) == SUMMARY_KEYS
    assert summary["rows_scanned"] == 1
    assert summary["counts_by_primary"].get("quote_request_inbound") == 1
    assert len(payload["review_csv_rows"]) == 1
    assert payload["review_csv_rows"][0]["predicted_label"] == "quote_request_inbound"

    csv_path = tmp_path / "review.csv"
    write_review_csv(csv_path, payload["review_csv_rows"])
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(REVIEW_CSV_FIELDS)
        rows = list(reader)
    assert len(rows) == 1

    full = attach_audit_meta(payload, db_path=db, days=800, limit=100)
    assert full["meta"]["sqlite_path"] == str(db.resolve())
    assert "baseline_comparison" in full


def test_cli_help() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    for flag in ("--db", "--days", "--limit", "--json", "--out", "--csv-out", "--no-csv", "--legacy-also"):
        assert flag in r.stdout


def test_cli_json_smoke_matches_library(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    _seed_db(db)
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    cp = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--days",
            "800",
            "--limit",
            "100",
            "--json",
            "--no-csv",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert cp.returncode == 0, cp.stderr + cp.stdout
    payload = json.loads(cp.stdout)
    assert payload["summary"]["rows_scanned"] == 1
    assert payload["summary"]["counts_by_primary"].get("quote_request_inbound") == 1
    assert set(payload["summary"]) == SUMMARY_KEYS
