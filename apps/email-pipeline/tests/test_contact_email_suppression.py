from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.contact_email_suppression import (
    operator_contact_suppression_rw_enabled,
    streamlit_contact_suppression_rw_enabled,
    contact_email_suppression_table_exists,
    delete_contact_email_suppression,
    ensure_contact_email_suppression_table,
    fetch_contact_email_suppression_map,
    fetch_contact_email_suppression_row,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)


def test_validate_contact_email_suppression_payload_normalizes_email() -> None:
    payload = validate_contact_email_suppression_payload(
        email="  Foo.Bar@Example.cl ",
        suppression_reason_code="bounce_no_such_user",
        suppression_reason_text="550 5.1.1 no such user",
        suppression_source="gmail bounce",
        last_bounced_at="2026-03-31T15:16:26Z",
        updated_by="tester",
    )
    assert payload.email == "foo.bar@example.cl"
    assert payload.suppression_reason_code == "bounce_no_such_user"


def test_contact_email_suppression_roundtrip() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        ensure_contact_email_suppression_table(conn)
        assert contact_email_suppression_table_exists(conn) is True
        payload = validate_contact_email_suppression_payload(
            email="contacto@example.cl",
            suppression_reason_code="bounce_access_denied",
            suppression_reason_text="550 5.4.1 access denied",
            suppression_source="gmail bounce",
            last_bounced_at="2026-03-31T15:16:26Z",
            updated_by="tester",
        )
        upsert_contact_email_suppression(conn, payload=payload, at_iso="2026-03-31T16:00:00Z")
        row = fetch_contact_email_suppression_row(conn, "contacto@example.cl")
        assert row is not None
        assert row["suppression_reason_code"] == "bounce_access_denied"
        assert row["updated_at"] == "2026-03-31T16:00:00Z"

        mapping = fetch_contact_email_suppression_map(
            conn, ["contacto@example.cl", "otra@example.cl"]
        )
        assert "contacto@example.cl" in mapping
        assert "otra@example.cl" not in mapping

        delete_contact_email_suppression(conn, "contacto@example.cl")
        assert fetch_contact_email_suppression_row(conn, "contacto@example.cl") is None
    finally:
        conn.close()


def test_operator_contact_suppression_rw_new_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_OPERATOR_CONTACT_SUPPRESSION_RW", raising=False)
    monkeypatch.delenv("ORIGENLAB_STREAMLIT_CONTACT_SUPPRESSION_RW", raising=False)
    assert operator_contact_suppression_rw_enabled() is False
    monkeypatch.setenv("ORIGENLAB_OPERATOR_CONTACT_SUPPRESSION_RW", "1")
    assert operator_contact_suppression_rw_enabled() is True


def test_operator_contact_suppression_rw_legacy_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_OPERATOR_CONTACT_SUPPRESSION_RW", raising=False)
    monkeypatch.setenv("ORIGENLAB_STREAMLIT_CONTACT_SUPPRESSION_RW", "1")
    assert operator_contact_suppression_rw_enabled() is True
    assert streamlit_contact_suppression_rw_enabled() is True


def test_operator_contact_suppression_rw_new_env_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_OPERATOR_CONTACT_SUPPRESSION_RW", "0")
    monkeypatch.setenv("ORIGENLAB_STREAMLIT_CONTACT_SUPPRESSION_RW", "1")
    assert operator_contact_suppression_rw_enabled() is False
