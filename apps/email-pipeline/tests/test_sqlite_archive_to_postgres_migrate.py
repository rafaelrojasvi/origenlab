"""Tests for scripts/migrate/sqlite_archive_to_postgres.py (helpers + CLI preconditions)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from origenlab_email_pipeline.db import init_schema

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "migrate" / "sqlite_archive_to_postgres.py"


def _load():
    spec = importlib.util.spec_from_file_location("sqlite_archive_to_postgres", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def test_normalize_postgres_url_strips_sqlalchemy_driver() -> None:
    assert m.normalize_postgres_url("postgresql+psycopg://u@h/db") == "postgresql://u@h/db"
    assert m.normalize_postgres_url("postgresql://u@h/db") == "postgresql://u@h/db"


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
    with pytest.raises(m.ConversionError):
        m.int_to_bool_or_none(True, table="t", row_id=1, column="c")


def test_resolve_postgres_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="Postgres URL"):
        m.resolve_postgres_url(None)


def test_sqlite_missing_file_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--sqlite-db", str(tmp_path / "nope.sqlite")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2


def test_minimal_sqlite_strict_pass_missing_pg_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "a.sqlite"
    conn = __import__("sqlite3").connect(str(db))
    init_schema(conn)
    conn.execute("DELETE FROM attachment_extracts")
    conn.execute("DELETE FROM attachments")
    conn.execute("DELETE FROM emails")
    conn.execute(
        """
        INSERT INTO emails (source_file, message_id, date_iso, body, body_has_plain, body_has_html, has_attachments)
        VALUES ('x', 'm', '2024-01-01T00:00:00+00:00', 'b', 1, 0, 0)
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--sqlite-db", str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert "Postgres URL" in (r.stderr + r.stdout)


@pytest.mark.skipif(
    not os.environ.get("ORIGENLAB_POSTGRES_URL") and not os.environ.get("ALEMBIC_DATABASE_URL"),
    reason="Set ORIGENLAB_POSTGRES_URL or ALEMBIC_DATABASE_URL for integration test.",
)
def test_dry_run_connects_postgres(tmp_path: Path) -> None:
    db = tmp_path / "dry.sqlite"
    conn = __import__("sqlite3").connect(str(db))
    init_schema(conn)
    conn.execute("DELETE FROM attachment_extracts")
    conn.execute("DELETE FROM attachments")
    conn.execute("DELETE FROM emails")
    conn.execute(
        """
        INSERT INTO emails (source_file, message_id, date_iso, body, body_has_plain, body_has_html, has_attachments)
        VALUES ('x', 'm', '2024-01-01T00:00:00+00:00', 'b', 1, 0, 0)
        """
    )
    conn.commit()
    conn.close()
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--sqlite-db", str(db), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
