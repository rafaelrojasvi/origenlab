"""contact_domain_suppression sidecar DDL and load helpers."""

from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.contact_domain_suppression import (
    CONTACT_DOMAIN_SUPPRESSION_SCHEMA_SQL,
    ensure_contact_domain_suppression_table,
    load_suppressed_contact_domain_norms,
    upsert_contact_domain_suppression,
    validate_contact_domain_suppression_payload,
)


def test_schema_contains_table_name() -> None:
    assert "contact_domain_suppression" in CONTACT_DOMAIN_SUPPRESSION_SCHEMA_SQL


def test_ensure_and_roundtrip_load() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_contact_domain_suppression_table(conn)
    payload = validate_contact_domain_suppression_payload(
        domain="Example.CL",
        suppression_reason_text="test",
        updated_by="t",
    )
    upsert_contact_domain_suppression(conn, payload=payload)
    conn.commit()
    assert load_suppressed_contact_domain_norms(conn) == frozenset({"example.cl"})
    conn.close()


def test_validate_rejects_at_sign() -> None:
    with pytest.raises(ValueError):
        validate_contact_domain_suppression_payload(
            domain="a@b.cl",
            suppression_reason_text=None,
            updated_by=None,
        )
