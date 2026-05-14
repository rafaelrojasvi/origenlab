"""Tests for canonical vs legacy ``emails.source_file`` classification."""

from __future__ import annotations

import pytest

from origenlab_email_pipeline.canonical_contacto_source import (
    CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE,
    classify_email_source,
    is_canonical_contacto_gmail_source,
    sql_predicate_contacto_gmail_source,
)


@pytest.mark.parametrize(
    ("source_file", "expected"),
    [
        ("gmail:contacto@origenlab.cl/INBOX", "canonical_gmail"),
        ("gmail:contacto@origenlab.cl/[Gmail]/Enviados", "canonical_gmail"),
        ("/home/x/mbox/contacto@labdelivery.cl/Inbox/mbox", "legacy_labdelivery"),
        ("imap:contacto@origenlab.cl/INBOX", "imap"),
        ("gmail:other@x.com/INBOX", "other_gmail"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_classify_email_source(source_file: str | None, expected: str) -> None:
    assert classify_email_source(source_file) == expected


def test_is_canonical_contacto_gmail_source() -> None:
    assert is_canonical_contacto_gmail_source("gmail:contacto@origenlab.cl/INBOX") is True
    assert is_canonical_contacto_gmail_source("gmail:contacto@origenlab.cl") is False
    assert is_canonical_contacto_gmail_source(None) is False


def test_sql_predicate_uses_strict_workspace_like() -> None:
    assert CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE == "gmail:contacto@origenlab.cl/%"
    assert CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE in sql_predicate_contacto_gmail_source()
    assert sql_predicate_contacto_gmail_source() == "lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'"
