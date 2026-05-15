"""Operational vs archive scope helpers."""

from __future__ import annotations

import pytest

from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE
from origenlab_email_pipeline.operational_scope import (
    is_operational_noise_entity,
    normalize_data_scope,
    postgres_mart_relation,
    sqlite_canonical_emails_predicate,
)


def test_normalize_data_scope_defaults_canonical() -> None:
    assert normalize_data_scope(None) == "canonical"
    assert normalize_data_scope("archive") == "archive"
    assert normalize_data_scope("CANONICAL") == "canonical"


def test_postgres_mart_relation() -> None:
    assert postgres_mart_relation("contact_master", "canonical") == (
        "mart.contact_master_canonical"
    )
    assert postgres_mart_relation("contact_master", "archive") == "mart.contact_master"


def test_canonical_predicate_uses_gmail_prefix() -> None:
    pred = sqlite_canonical_emails_predicate("e")
    assert CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE in pred
    assert "e.source_file" in pred


@pytest.mark.parametrize(
    "kind,key",
    [
        ("contact", "mailer-daemon@google.com"),
        ("contact", "NOISE_SENDER"),
        ("organization", "postabg.delcon.it"),
        ("contact", "noreply@dhl.com"),
    ],
)
def test_operational_noise_entities(kind: str, key: str) -> None:
    assert is_operational_noise_entity(kind, key) is True


def test_operational_noise_allows_normal_lab_contact() -> None:
    assert is_operational_noise_entity("contact", "lab@universidad.cl") is False
