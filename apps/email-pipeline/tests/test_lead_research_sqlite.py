"""Tests for lead_research SQLite builder (Phase 10D)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.lead_research.lead_research_builder import (
    build_lead_research_sqlite,
    sqlite_lead_research_counts,
)
from origenlab_email_pipeline.lead_research.lead_research_mirror_read_model import (
    load_lead_research_mirror_payload,
)
from origenlab_email_pipeline.lead_research.lead_research_mirror_safety import (
    FORBIDDEN_MIRROR_KEYS,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import lead_research_tables_exist

_FIXTURES = Path(__file__).parent / "fixtures" / "lead_research"


def test_builder_dry_run_counts() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        summary = build_lead_research_sqlite(
            conn,
            review_csv=_FIXTURES / "mini_review.csv",
            blocked_csv=_FIXTURES / "mini_blocked.csv",
            dry_run=True,
        )
    finally:
        conn.close()
    assert summary["dry_run"] is True
    assert summary["prospects_review"] == 4
    assert summary["prospects_blocked"] == 1
    assert summary["net_new_safe"] == 1
    assert summary["public_tender_review"] == 1
    assert summary["same_domain_review"] == 1
    assert summary["research_needed"] == 1


def test_builder_writes_rows_and_mirror_safe() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        build_lead_research_sqlite(
            conn,
            review_csv=_FIXTURES / "mini_review.csv",
            blocked_csv=_FIXTURES / "mini_blocked.csv",
            batch_key="test_batch",
            dry_run=False,
        )
        assert lead_research_tables_exist(conn)
        counts = sqlite_lead_research_counts(conn)
        assert counts["prospects"] == 5
        assert counts["evidence"] >= 4
        assert counts["recommendations"] == 5

        payload = load_lead_research_mirror_payload(conn)
        for row in payload["prospects"]:
            for key in row:
                assert key not in FORBIDDEN_MIRROR_KEYS
        blocked = [p for p in payload["prospects"] if p["is_blocked"]]
        assert len(blocked) == 1
        assert blocked[0]["classification"] == "already_contacted_block"
    finally:
        conn.close()


def test_builder_idempotent_rerun() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        for _ in range(2):
            build_lead_research_sqlite(
                conn,
                review_csv=_FIXTURES / "mini_review.csv",
                blocked_csv=_FIXTURES / "mini_blocked.csv",
                batch_key="idem",
                dry_run=False,
            )
        assert sqlite_lead_research_counts(conn)["prospects"] == 5
        batches = conn.execute("SELECT COUNT(*) FROM lead_research_batch").fetchone()[0]
        assert batches == 1
    finally:
        conn.close()
