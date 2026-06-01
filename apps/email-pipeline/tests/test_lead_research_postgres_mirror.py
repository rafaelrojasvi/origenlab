"""Tests for lead_intel Postgres mirror sync + verify helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.lead_research.lead_research_builder import build_lead_research_sqlite
from origenlab_email_pipeline.lead_research.lead_research_builder import sqlite_lead_research_counts
from origenlab_email_pipeline.lead_research.lead_research_mirror_read_model import (
    load_lead_research_mirror_payload,
)
from origenlab_email_pipeline.lead_research.lead_research_postgres_mirror import (
    compare_lead_research_mirror_counts,
    pg_lead_intel_tables_exist,
    sync_lead_research_postgres_mirror,
)
from origenlab_email_pipeline.outreach_contact_state import ensure_outreach_contact_state_table
from origenlab_email_pipeline.contact_email_suppression import (
    ensure_contact_email_suppression_table,
)
from origenlab_email_pipeline.outreach_contact_state import (
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
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
    assert result["built_counts"]["block_reasons"] == result["sqlite_counts"]["block_reasons"]


def test_overlay_can_reduce_block_reasons_vs_raw_sqlite(tmp_path: Path) -> None:
    db = _seed_sqlite(tmp_path)
    conn = sqlite3.connect(db)
    ensure_outreach_contact_state_table(conn)
    ensure_contact_email_suppression_table(conn)
    upsert_outreach_contact_state(
        conn,
        payload=validate_outreach_contact_state_payload(
            contact_email="contacto@acme.cl",
            state="contacted",
            source="test_overlay",
        ),
    )
    conn.commit()
    raw = sqlite_lead_research_counts(conn)
    built = len(load_lead_research_mirror_payload(conn)["block_reasons"])
    conn.close()
    assert built < raw["block_reasons"]


def test_compare_mirror_counts_detects_postgres_gap() -> None:
    built = {
        "prospects": 5,
        "evidence": 5,
        "recommendations": 5,
        "block_reasons": 4,
    }
    pg_ok = {"prospect": 5, "evidence": 5, "recommendation": 5, "block_reason": 4}
    assert compare_lead_research_mirror_counts(built, pg_ok) == []
    pg_missing = {**pg_ok, "block_reason": 3}
    errors = compare_lead_research_mirror_counts(built, pg_missing)
    assert any("block_reason" in e for e in errors)


def test_pg_tables_exist_helper() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    assert pg_lead_intel_tables_exist(cur) is True
    cur.fetchone.return_value = None
    assert pg_lead_intel_tables_exist(cur) is False
