"""Tests for read-only Prospectos safety drift audit."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from origenlab_email_pipeline.contact_email_suppression import (
    ensure_contact_email_suppression_table,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import ensure_lead_research_tables
from origenlab_email_pipeline.lead_research.lead_research_operational_overlay import (
    CLASS_SAME_DOMAIN_CONTACTED_REVIEW,
)
from origenlab_email_pipeline.lead_research.prospectos_safety_drift import (
    run_prospectos_safety_drift_audit,
)
from origenlab_email_pipeline.outreach_contact_state import (
    ensure_outreach_contact_state_table,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)

_FIXED_AT = "2026-06-01T12:00:00+00:00"


def _seed_batch(conn: sqlite3.Connection) -> int:
    ensure_lead_research_tables(conn)
    conn.execute(
        """
        INSERT INTO lead_research_batch (batch_key, source_name, row_count, created_at)
        VALUES ('test-batch', 'test', 4, ?)
        """,
        (_FIXED_AT,),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_prospect(
    conn: sqlite3.Connection,
    *,
    batch_id: int,
    prospect_key: str,
    email: str | None,
    classification: str,
    status: str,
    is_blocked: int,
    domain: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO lead_research_prospect (
          batch_id, prospect_key, organization_name, email, domain,
          input_priority_score, final_score, classification, status,
          campaign_bucket, is_blocked, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, 0, 50, ?, ?, 'other', ?, 1, ?)
        """,
        (
            batch_id,
            prospect_key,
            f"Org {prospect_key}",
            email,
            domain or (email.split("@")[-1] if email else ""),
            classification,
            status,
            is_blocked,
            _FIXED_AT,
        ),
    )


@pytest.fixture
def drift_db(tmp_path: Path) -> Path:
    db = tmp_path / "drift.sqlite"
    conn = sqlite3.connect(db)
    ensure_contact_email_suppression_table(conn)
    ensure_outreach_contact_state_table(conn)
    batch_id = _seed_batch(conn)

    _insert_prospect(
        conn,
        batch_id=batch_id,
        prospect_key="supp-mismatch",
        email="bounced@example.com",
        classification="net_new_safe_review",
        status="net_new_safe_review",
        is_blocked=0,
    )
    upsert_contact_email_suppression(
        conn,
        payload=validate_contact_email_suppression_payload(
            email="bounced@example.com",
            suppression_reason_code="bounce_no_such_user",
            suppression_reason_text="test",
            suppression_source="test",
            last_bounced_at=_FIXED_AT,
            updated_by="test",
        ),
    )

    _insert_prospect(
        conn,
        batch_id=batch_id,
        prospect_key="contacted-mismatch",
        email="sent@client.cl",
        classification="same_domain_contacted_review",
        status="same_domain_review",
        is_blocked=0,
    )
    upsert_outreach_contact_state(
        conn,
        payload=validate_outreach_contact_state_payload(
            contact_email="sent@client.cl",
            state="contacted",
            source="test",
        ),
    )

    _insert_prospect(
        conn,
        batch_id=batch_id,
        prospect_key="reviewable-blocked",
        email="also-sent@client.cl",
        classification="public_tender_review",
        status="public_tender_review",
        is_blocked=0,
    )
    upsert_outreach_contact_state(
        conn,
        payload=validate_outreach_contact_state_payload(
            contact_email="also-sent@client.cl",
            state="contacted",
            source="test",
        ),
    )

    _insert_prospect(
        conn,
        batch_id=batch_id,
        prospect_key="no-email",
        email=None,
        classification="research_only_contact_needed",
        status="research_needed",
        is_blocked=0,
    )

    _insert_prospect(
        conn,
        batch_id=batch_id,
        prospect_key="falta-domain-contacted",
        email=None,
        classification="research_only_contact_needed",
        status="research_needed",
        is_blocked=0,
        domain="client.cl",
    )
    upsert_outreach_contact_state(
        conn,
        payload=validate_outreach_contact_state_payload(
            contact_email="other@client.cl",
            state="contacted",
            source="test",
        ),
    )

    conn.commit()
    conn.close()
    return db


def test_reports_suppressed_not_raw_blocked(drift_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    conn = sqlite3.connect(drift_db)
    try:
        result = run_prospectos_safety_drift_audit(
            conn,
            sqlite_path=drift_db,
            out_dir=out,
            generated_at=_FIXED_AT,
        )
    finally:
        conn.close()

    assert result.summary["suppressed_not_raw_blocked_count"] == 1
    assert result.suppressed_not_raw_blocked[0]["email"] == "bounced@example.com"
    assert (out / "suppressed_prospects_not_raw_blocked.csv").is_file()


def test_reports_contacted_not_raw_contacted(drift_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out2"
    conn = sqlite3.connect(drift_db)
    try:
        result = run_prospectos_safety_drift_audit(
            conn, sqlite_path=drift_db, out_dir=out, generated_at=_FIXED_AT
        )
    finally:
        conn.close()

    assert result.summary["contacted_not_raw_contacted_count"] >= 1
    emails = {row["email"] for row in result.contacted_not_raw_contacted}
    assert "sent@client.cl" in emails


def test_reports_net_new_raw_but_blocked_by_safety(drift_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out3"
    conn = sqlite3.connect(drift_db)
    try:
        result = run_prospectos_safety_drift_audit(
            conn, sqlite_path=drift_db, out_dir=out, generated_at=_FIXED_AT
        )
    finally:
        conn.close()

    assert result.summary["net_new_raw_but_safety_blocked_count"] >= 1
    assert any(
        "outreach:contacted" in row["operational_blockers"]
        for row in result.net_new_raw_but_blocked_by_safety
    )


def test_reports_missing_email_rows(drift_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out4"
    conn = sqlite3.connect(drift_db)
    try:
        result = run_prospectos_safety_drift_audit(
            conn, sqlite_path=drift_db, out_dir=out, generated_at=_FIXED_AT
        )
    finally:
        conn.close()

    assert result.summary["prospects_missing_email"] == 2
    assert len(result.missing_email) == 2


def test_empty_email_same_domain_overlay_in_drift_audit(drift_db: Path, tmp_path: Path) -> None:
    from origenlab_email_pipeline.lead_research.lead_research_mirror_read_model import (
        load_lead_research_mirror_payload,
    )

    conn = sqlite3.connect(drift_db)
    try:
        row = next(
            p
            for p in load_lead_research_mirror_payload(conn)["prospects"]
            if p["prospect_key"] == "falta-domain-contacted"
        )
    finally:
        conn.close()
    assert row["classification"] == CLASS_SAME_DOMAIN_CONTACTED_REVIEW
    assert not row.get("email")


def test_no_db_writes(drift_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out5"
    conn = sqlite3.connect(drift_db)
    before = conn.execute("SELECT COUNT(*) FROM lead_research_prospect").fetchone()[0]
    try:
        run_prospectos_safety_drift_audit(
            conn, sqlite_path=drift_db, out_dir=out, generated_at=_FIXED_AT
        )
        after = conn.execute("SELECT COUNT(*) FROM lead_research_prospect").fetchone()[0]
    finally:
        conn.close()
    assert before == after == 5


def test_deterministic_summary_and_sort(drift_db: Path, tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    for out in (out_a, out_b):
        conn = sqlite3.connect(drift_db)
        try:
            run_prospectos_safety_drift_audit(
                conn, sqlite_path=drift_db, out_dir=out, generated_at=_FIXED_AT
            )
        finally:
            conn.close()

    summary_a = json.loads((out_a / "prospectos_safety_drift_summary.json").read_text(encoding="utf-8"))
    summary_b = json.loads((out_b / "prospectos_safety_drift_summary.json").read_text(encoding="utf-8"))
    assert summary_a == summary_b
    assert summary_a["generated_at"] == _FIXED_AT

    csv_text = (out_a / "suppressed_prospects_not_raw_blocked.csv").read_text(encoding="utf-8")
    assert csv_text == (out_b / "suppressed_prospects_not_raw_blocked.csv").read_text(encoding="utf-8")


def test_strict_exit_code_thresholds(drift_db: Path, tmp_path: Path) -> None:
    conn = sqlite3.connect(drift_db)
    try:
        result = run_prospectos_safety_drift_audit(
            conn,
            sqlite_path=drift_db,
            out_dir=tmp_path / "strict",
            generated_at=_FIXED_AT,
        )
    finally:
        conn.close()

    assert result.exit_code_strict(max_suppressed_raw_mismatch=0, max_net_new_blocked=0) == 2
    assert result.exit_code_strict(max_suppressed_raw_mismatch=10, max_net_new_blocked=10) == 0
