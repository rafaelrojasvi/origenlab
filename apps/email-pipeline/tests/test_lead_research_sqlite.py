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
        assert counts["evidence"] >= 5
        assert counts["recommendations"] == 5
        blocked_row = conn.execute(
            """
            SELECT input_priority_score, sector, product_angle, evidence_url
            FROM lead_research_prospect WHERE is_blocked = 1
            """
        ).fetchone()
        assert blocked_row[0] == 82
        assert blocked_row[1] == "Laboratorios privados"
        assert "incubadoras" in (blocked_row[2] or "")
        assert blocked_row[3]

        payload = load_lead_research_mirror_payload(conn)
        for row in payload["prospects"]:
            for key in row:
                assert key not in FORBIDDEN_MIRROR_KEYS
        blocked = [p for p in payload["prospects"] if p["is_blocked"]]
        assert len(blocked) == 1
        b0 = blocked[0]
        assert b0["classification"] == "already_contacted_block"
        assert b0["organization_name"] == "5M S.A."
        assert b0["sector"] == "Laboratorios privados"
        assert b0["buyer_type"] == "laboratorio_acuicola"
        assert b0["product_angle"] == "incubadoras; balances; sample prep; QC"
        assert b0["evidence_url"]
        assert b0["final_score"] == 0
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
