"""Tests for scripts/migrate/sqlite_mart_core_to_postgres.py."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from datetime import timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "migrate" / "sqlite_mart_core_to_postgres.py"


def _load():
    spec = importlib.util.spec_from_file_location("sqlite_mart_core_to_postgres", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _make_mart_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE contact_master (
          email TEXT PRIMARY KEY,
          contact_name_best TEXT,
          domain TEXT,
          organization_name_guess TEXT,
          organization_type_guess TEXT,
          first_seen_at TEXT,
          last_seen_at TEXT,
          total_emails INTEGER,
          inbound_emails INTEGER,
          outbound_emails INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          business_doc_email_count INTEGER,
          quote_doc_count INTEGER,
          invoice_doc_count INTEGER,
          top_equipment_tags TEXT,
          confidence_score REAL
        );
        CREATE TABLE organization_master (
          domain TEXT PRIMARY KEY,
          organization_name_guess TEXT,
          organization_type_guess TEXT,
          first_seen_at TEXT,
          last_seen_at TEXT,
          total_emails INTEGER,
          total_contacts INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          business_doc_email_count INTEGER,
          quote_doc_count INTEGER,
          invoice_doc_count INTEGER,
          top_equipment_tags TEXT,
          key_contacts TEXT
        );
        CREATE TABLE opportunity_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          email_id INTEGER,
          attachment_id INTEGER,
          score REAL,
          details_json TEXT,
          created_at TEXT
        );
        INSERT INTO contact_master (
          email, contact_name_best, domain, last_seen_at, total_emails, confidence_score
        ) VALUES (
          'lab@example.cl', 'Lab', 'example.cl', '2024-06-01T00:00:00Z', 3, 0.9
        );
        INSERT INTO organization_master (
          domain, organization_name_guess, last_seen_at, total_emails, total_contacts
        ) VALUES (
          'example.cl', 'Example Org', '2024-06-01T00:00:00Z', 10, 2
        );
        INSERT INTO opportunity_signals (
          id, signal_type, entity_kind, entity_key, score, details_json, created_at
        ) VALUES (
          1, 'quote_mention', 'contact', 'lab@example.cl', 0.8,
          '{"reason":"test"}', '2024-06-01T00:00:00Z'
        );
        """
    )
    conn.commit()
    conn.close()


def test_scratch_url_guard_rejects_unknown_host() -> None:
    with pytest.raises(ValueError, match="scratch/staging"):
        m.assert_scratch_postgres_target(
            "postgresql://u:p@prod-db.internal/acme_production",
            allow_non_scratch=False,
        )


def test_scratch_url_guard_allows_localhost() -> None:
    m.assert_scratch_postgres_target(
        "postgresql://u:p@127.0.0.1:5432/origenlab_scratch",
        allow_non_scratch=False,
    )


def test_missing_sqlite_mart_table_warning(tmp_path: Path) -> None:
    db = tmp_path / "partial.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE contact_master (email TEXT PRIMARY KEY, contact_name_best TEXT)"
    )
    conn.commit()
    counts, warnings, exists = m.collect_sqlite_source_counts(conn, m.TABLE_SPECS)
    conn.close()
    assert counts["contact_master"] == 0
    assert exists["organization_master"] is False
    assert any("organization_master" in w for w in warnings)


def test_parse_jsonb_python() -> None:
    assert m.parse_jsonb_python('{"a":1}') == {"a": 1}
    assert m.parse_jsonb_python("not-json") == {"raw": "not-json"}
    assert m.parse_jsonb_python(None) is None
    assert m.parse_jsonb_python("") is None
    assert m.parse_jsonb_python({"k": "v"}) == {"k": "v"}


def test_adapt_jsonb_for_postgres_wraps_dict() -> None:
    from psycopg.types.json import Json

    wrapped = m.adapt_jsonb_for_postgres('{"reason":"test","tags":["x"]}')
    assert isinstance(wrapped, Json)
    assert wrapped.obj == {"reason": "test", "tags": ["x"]}
    assert m.adapt_jsonb_for_postgres(None) is None
    plain = m.adapt_jsonb_for_postgres("plain")
    assert isinstance(plain, Json)
    assert plain.obj == {"raw": "plain"}


def test_convert_row_details_json_is_json_adapter() -> None:
    from psycopg.types.json import Json

    spec = next(s for s in m.TABLE_SPECS if s["source"] == "opportunity_signals")
    row = (
        42,
        "quote_mention",
        "contact",
        "lab@example.cl",
        100,
        None,
        0.75,
        '{"nested":{"n":1},"items":[1,2]}',
        "2024-06-01T00:00:00Z",
    )
    converted = m._convert_row(
        row,
        table="opportunity_signals",
        pk="id",
        columns=tuple(spec["columns"]),
        timestamp_columns=frozenset(spec.get("timestamp_columns") or ()),
        json_columns=frozenset(spec.get("json_columns") or ()),
    )
    details = converted[spec["columns"].index("details_json")]
    assert isinstance(details, Json)
    assert details.obj == {"nested": {"n": 1}, "items": [1, 2]}
    assert isinstance(converted[spec["columns"].index("signal_type")], str)


def test_timestamp_conversion() -> None:
    dt = m.iso_text_to_datetime("2024-01-01T00:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def _postgres_test_url() -> str | None:
    return (os.environ.get("ORIGENLAB_POSTGRES_TEST_URL") or os.environ.get("ORIGENLAB_POSTGRES_URL") or "").strip() or None


@pytest.mark.skipif(
    _postgres_test_url() is None,
    reason="Set ORIGENLAB_POSTGRES_TEST_URL or ORIGENLAB_POSTGRES_URL for integration tests.",
)
def test_dry_run_integration(tmp_path: Path) -> None:
    db = tmp_path / "mart.sqlite"
    _make_mart_sqlite(db)
    pg_url = _postgres_test_url()
    assert pg_url
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--sqlite-db",
            str(db),
            "--postgres-url",
            pg_url,
            "--dry-run",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout


@pytest.mark.skipif(
    _postgres_test_url() is None,
    reason="Set ORIGENLAB_POSTGRES_TEST_URL or ORIGENLAB_POSTGRES_URL for integration tests.",
)
def test_replace_loads_opportunity_signals_jsonb(tmp_path: Path) -> None:
    """Regression: details_json must use psycopg Json, not raw dict."""
    db = tmp_path / "mart.sqlite"
    _make_mart_sqlite(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO opportunity_signals (
          id, signal_type, entity_kind, entity_key, score, details_json, created_at
        ) VALUES
          (2, 'nested', 'contact', 'b@example.cl', 0.5,
           '{"nested":{"x":1},"list":[1,2]}', '2024-06-02T00:00:00Z'),
          (3, 'invalid_json', 'domain', 'example.cl', 0.1,
           'not-valid-json{{{', '2024-06-03T00:00:00Z'),
          (4, 'null_details', 'contact', 'c@example.cl', 0.2,
           NULL, '2024-06-04T00:00:00Z')
        """
    )
    conn.commit()
    conn.close()

    pg_url = _postgres_test_url()
    assert pg_url
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--sqlite-db",
            str(db),
            "--postgres-url",
            pg_url,
            "--replace",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "migration completed" in r.stdout

    import psycopg

    with psycopg.connect(pg_url) as pconn:
        with pconn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mart.opportunity_signals")
            assert int(cur.fetchone()[0]) == 4
            cur.execute(
                """
                SELECT details_json
                FROM mart.opportunity_signals
                WHERE id = 2
                """
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == {"nested": {"x": 1}, "list": [1, 2]}
            cur.execute(
                "SELECT details_json FROM mart.opportunity_signals WHERE id = 3"
            )
            assert cur.fetchone()[0] == {"raw": "not-valid-json{{{"}
            cur.execute(
                "SELECT details_json FROM mart.opportunity_signals WHERE id = 4"
            )
            assert cur.fetchone()[0] is None
