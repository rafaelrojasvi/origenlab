"""Tests for outreach_contact_state sidecar DDL and upsert helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.outreach_contact_state import (
    OUTREACH_CONTACT_STATE_SCHEMA_SQL,
    OutreachContactStatePayload,
    ensure_outreach_contact_state_table,
    fetch_outreach_contact_state_row,
    normalize_contact_email_for_outreach,
    outreach_contact_state_table_exists,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)


def test_ddl_contains_create_table_and_primary_key() -> None:
    assert "CREATE TABLE IF NOT EXISTS outreach_contact_state" in OUTREACH_CONTACT_STATE_SCHEMA_SQL
    assert "contact_email_norm TEXT PRIMARY KEY" in OUTREACH_CONTACT_STATE_SCHEMA_SQL
    assert "lead_id INTEGER" in OUTREACH_CONTACT_STATE_SCHEMA_SQL
    assert "REFERENCES" not in OUTREACH_CONTACT_STATE_SCHEMA_SQL


def test_ensure_creates_table_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db))
    assert not outreach_contact_state_table_exists(conn)
    ensure_outreach_contact_state_table(conn)
    assert outreach_contact_state_table_exists(conn)
    ensure_outreach_contact_state_table(conn)
    conn.close()


def test_normalize_contact_email() -> None:
    assert normalize_contact_email_for_outreach("  Person@Example.CL ") == "person@example.cl"


def test_normalize_rejects_multi_or_invalid() -> None:
    with pytest.raises(ValueError, match="no válido"):
        normalize_contact_email_for_outreach("")
    with pytest.raises(ValueError, match="no válido"):
        normalize_contact_email_for_outreach("not-an-email")


def test_validate_state_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Estado no válido"):
        validate_outreach_contact_state_payload(
            contact_email="a@b.cl",
            state="banana",
        )


def test_validate_lead_id() -> None:
    with pytest.raises(ValueError, match="lead_id"):
        validate_outreach_contact_state_payload(
            contact_email="a@b.cl",
            state="contacted",
            lead_id=True,  # bool is not a valid lead id
        )
    with pytest.raises(ValueError, match="lead_id"):
        validate_outreach_contact_state_payload(
            contact_email="a@b.cl",
            state="contacted",
            lead_id=0,
        )
    p = validate_outreach_contact_state_payload(
        contact_email="a@b.cl",
        state="replied",
        lead_id=42,
    )
    assert p.lead_id == 42


def test_upsert_insert_then_update(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db))
    ensure_outreach_contact_state_table(conn)

    p1 = validate_outreach_contact_state_payload(
        contact_email="lead@cliente.cl",
        state="not_contacted",
        source="operator",
        notes="pending",
        updated_by="test",
    )
    upsert_outreach_contact_state(conn, payload=p1, at_iso="2026-04-01T12:00:00Z")
    conn.commit()

    row = fetch_outreach_contact_state_row(conn, "lead@cliente.cl")
    assert row is not None
    assert row["state"] == "not_contacted"
    assert row["source"] == "operator"
    assert row["updated_at"] == "2026-04-01T12:00:00Z"
    assert row["lead_id"] is None

    p2 = validate_outreach_contact_state_payload(
        contact_email="lead@cliente.cl",
        state="contacted",
        first_contacted_at="2026-04-02",
        last_contacted_at="2026-04-02",
        source="operator",
        updated_by="test2",
        lead_id=7,
    )
    upsert_outreach_contact_state(conn, payload=p2, at_iso="2026-04-02T15:00:00Z")
    conn.commit()

    row2 = fetch_outreach_contact_state_row(conn, "lead@cliente.cl")
    assert row2 is not None
    assert row2["state"] == "contacted"
    assert row2["first_contacted_at"] == "2026-04-02"
    assert row2["last_contacted_at"] == "2026-04-02"
    assert row2["notes"] is None
    assert row2["lead_id"] == 7
    assert row2["updated_at"] == "2026-04-02T15:00:00Z"
    assert row2["updated_by"] == "test2"

    conn.close()


def test_fetch_invalid_email_returns_none(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    ensure_outreach_contact_state_table(conn)
    assert fetch_outreach_contact_state_row(conn, "@@@") is None
    conn.close()


def test_upsert_accepts_payload_dataclass(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    ensure_outreach_contact_state_table(conn)
    payload = OutreachContactStatePayload(
        contact_email_norm="x@y.cl",
        state="snoozed",
        first_contacted_at=None,
        last_contacted_at=None,
        source=None,
        notes=None,
        updated_by=None,
        lead_id=None,
    )
    upsert_outreach_contact_state(conn, payload=payload, at_iso="2026-01-01T00:00:00Z")
    conn.commit()
    r = fetch_outreach_contact_state_row(conn, "x@y.cl")
    assert r is not None and r["state"] == "snoozed"
    conn.close()
