"""Contract: Gmail contacto ``source_file`` predicates stay aligned across consumers."""

from __future__ import annotations

from origenlab_email_pipeline.cases_review_queue import CONTACTO_GMAIL_SOURCE_SQL as crq_constant
from origenlab_email_pipeline.contacto_gmail_source import (
    CONTACTO_GMAIL_SOURCE_SQL,
    sql_predicate_contacto_gmail_source,
)
from origenlab_email_pipeline.tatiana_copilot.draft_review_helpers import (
    load_contacto_gmail_email_choices_df,
)


def test_canonical_coalesce_unqualified_matches_legacy_literal() -> None:
    assert (
        CONTACTO_GMAIL_SOURCE_SQL
        == "lower(COALESCE(source_file, '')) LIKE 'gmail:contacto@origenlab.cl/%'"
    )
    assert sql_predicate_contacto_gmail_source(coalesce_null=True) == CONTACTO_GMAIL_SOURCE_SQL


def test_coalesce_qualified_e_matches_legacy_cases_review_inner_query() -> None:
    assert (
        sql_predicate_contacto_gmail_source(table_alias="e", coalesce_null=True)
        == "lower(COALESCE(e.source_file, '')) LIKE 'gmail:contacto@origenlab.cl/%'"
    )


def test_non_coalesce_unqualified_matches_mart_and_shared_predicate_forms() -> None:
    assert (
        sql_predicate_contacto_gmail_source()
        == "lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'"
    )


def test_cases_review_queue_reexports_same_constant() -> None:
    assert crq_constant is CONTACTO_GMAIL_SOURCE_SQL


def test_contacto_gmail_email_choices_query_runs_with_shared_predicate(tmp_path) -> None:
    db = tmp_path / "g.sqlite"
    conn = __import__("sqlite3").connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, subject TEXT, sender TEXT, source_file TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (1, '2026-01-01', 'S', 'a@b', 'gmail:contacto@origenlab.cl/inbox')"
    )
    conn.commit()
    df = load_contacto_gmail_email_choices_df(conn, limit=10)
    assert len(df) == 1
    conn.close()
