"""Tests for lead_intel Postgres mirror sync + verify helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.lead_research.lead_research_builder import build_lead_research_sqlite
from origenlab_email_pipeline.lead_research.lead_research_postgres_mirror import (
    pg_lead_intel_tables_exist,
    sync_lead_research_postgres_mirror,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "lead_research"


def _seed_sqlite(tmp_path: Path) -> Path:
    db = tmp_path / "lead.sqlite"
    conn = sqlite3.connect(db)
    try:
        build_lead_research_sqlite(
            conn,
            review_csv=_FIXTURES / "mini_review.csv",
            blocked_csv=_FIXTURES / "mini_blocked.csv",
            dry_run=False,
        )
    finally:
        conn.close()
    return db


def test_sync_skips_when_postgres_tables_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _seed_sqlite(tmp_path)

    class _FakeConn:
        def cursor(self) -> MagicMock:
            return MagicMock()

        def __enter__(self) -> "_FakeConn":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "origenlab_email_pipeline.lead_research.lead_research_postgres_mirror.psycopg.connect",
        lambda *args, **kwargs: _FakeConn(),
    )
    monkeypatch.setattr(
        "origenlab_email_pipeline.lead_research.lead_research_postgres_mirror.pg_lead_intel_tables_exist",
        lambda cur: False,
    )

    result = sync_lead_research_postgres_mirror(
        "postgresql://u:p@localhost/db",
        db,
        dry_run=False,
    )
    assert result.get("skipped") is True
    assert result.get("reason") == "table_missing"


def test_sync_dry_run_reports_built_counts(tmp_path: Path) -> None:
    db = _seed_sqlite(tmp_path)
    result = sync_lead_research_postgres_mirror("postgresql://u:p@localhost/db", db, dry_run=True)
    assert result["built_counts"]["prospects"] == 5


def test_pg_tables_exist_helper() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    assert pg_lead_intel_tables_exist(cur) is True
    cur.fetchone.return_value = None
    assert pg_lead_intel_tables_exist(cur) is False
