"""Tests for scripts/migrate/sqlite_document_master_to_postgres.py."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
from datetime import timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "migrate" / "sqlite_document_master_to_postgres.py"


def _load():
    spec = importlib.util.spec_from_file_location("sqlite_document_master_to_postgres", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _make_source_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE document_master (
          attachment_id INTEGER PRIMARY KEY,
          email_id INTEGER,
          filename TEXT,
          extension TEXT,
          sender_email TEXT,
          sender_domain TEXT,
          recipient_domain TEXT,
          sent_at TEXT,
          doc_type TEXT,
          extracted_preview_raw TEXT,
          extracted_preview_clean TEXT,
          preview_quality_score REAL,
          has_quote_terms INTEGER,
          has_invoice_terms INTEGER,
          has_purchase_terms INTEGER,
          has_price_list_terms INTEGER,
          equipment_tags TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO document_master (
          attachment_id, email_id, filename, sent_at, doc_type,
          has_quote_terms, has_invoice_terms, has_purchase_terms, has_price_list_terms
        ) VALUES (1, 10, 'a.pdf', '2024-01-01T00:00:00Z', 'quote', 1, 0, 0, 1)
        """
    )
    conn.commit()
    conn.close()


def test_default_batch_size_is_500() -> None:
    args = m.build_parser().parse_args([])
    assert args.batch_size == 500


def test_iso_text_to_datetime_z_and_null() -> None:
    assert m.iso_text_to_datetime(None) is None
    dt = m.iso_text_to_datetime("2024-01-01T00:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    naive = m.iso_text_to_datetime("2024-01-01T00:00:00")
    assert naive is not None
    assert naive.tzinfo == timezone.utc


def test_int_to_bool_or_none() -> None:
    assert m.int_to_bool_or_none(None, table="t", row_id=1, column="c") is None
    assert m.int_to_bool_or_none(0, table="t", row_id=1, column="c") is False
    assert m.int_to_bool_or_none(1, table="t", row_id=1, column="c") is True
    with pytest.raises(m.ConversionError):
        m.int_to_bool_or_none(2, table="t", row_id=1, column="c")


def test_resolve_postgres_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="Postgres URL"):
        m.resolve_postgres_url(None)


def test_missing_source_table_fails_before_postgres(tmp_path: Path) -> None:
    db = tmp_path / "no_dm.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE x(id INTEGER)")
    conn.commit()
    conn.close()
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--sqlite-db", str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert "document_master" in (r.stderr + r.stdout)


def test_target_nonempty_without_replace_fails_decision() -> None:
    assert m.should_refuse_nonempty(target_nonempty=True, replace=False, dry_run=False) is True
    assert m.should_refuse_nonempty(target_nonempty=True, replace=True, dry_run=False) is False
    assert m.should_refuse_nonempty(target_nonempty=True, replace=False, dry_run=True) is False


def test_progress_formatter_shape() -> None:
    line = m.format_load_progress(
        pg_table="mart.document_master",
        loaded_so_far=1200,
        total=12266,
        elapsed_s=13.2,
        batch_len=500,
    )
    assert "mart.document_master" in line
    assert "1200/12266" in line
    assert "elapsed=13.2s" in line
    assert "batch=500" in line


def test_json_summary_shape() -> None:
    doc = m._empty_result()
    assert set(
        [
            "ok",
            "dry_run",
            "replace",
            "sqlite_counts",
            "postgres_counts_before",
            "postgres_counts_after",
            "loaded",
            "validation",
            "errors",
            "warnings",
            "elapsed_seconds",
        ]
    ).issubset(set(doc.keys()))
    assert "rows" not in doc
    assert "row_ids" not in doc


@pytest.mark.skipif(
    not os.environ.get("ORIGENLAB_POSTGRES_TEST_URL"),
    reason="Set ORIGENLAB_POSTGRES_TEST_URL for optional integration test.",
)
def test_dry_run_does_not_write_integration(tmp_path: Path) -> None:
    db = tmp_path / "dm.sqlite"
    _make_source_db(db)
    url = os.environ["ORIGENLAB_POSTGRES_TEST_URL"]
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--sqlite-db",
            str(db),
            "--postgres-url",
            url,
            "--dry-run",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
