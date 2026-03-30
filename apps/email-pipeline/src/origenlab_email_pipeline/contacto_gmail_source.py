"""Canonical SQL for Gmail-ingested contacto@origenlab.cl rows (emails.source_file).

Streamlit «Actividad / Casos / Borrador Gmail» and ``cases_review_queue`` filter the same
workspace-ingest prefix. Keep predicates here so wording cannot drift.
"""

from __future__ import annotations

# SQL LIKE operand (quoted), shared by all predicates below.
CONTACTO_GMAIL_LIKE = "LIKE 'gmail:contacto@origenlab.cl%'"


def sql_predicate_contacto_gmail_source(
    *,
    table_alias: str | None = None,
    coalesce_null: bool = False,
) -> str:
    """Return ``lower(...) {CONTACTO_GMAIL_LIKE}`` for use in WHERE clauses.

    ``coalesce_null=True`` matches legacy forms that treat NULL ``source_file`` as empty string
    (e.g. ``cases_review_queue``). ``coalesce_null=False`` matches ``lower(source_file)`` forms
    used elsewhere (NULL still does not match the LIKE).
    """
    col = "source_file" if table_alias is None else f"{table_alias}.source_file"
    expr = f"lower(COALESCE({col}, ''))" if coalesce_null else f"lower({col})"
    return f"{expr} {CONTACTO_GMAIL_LIKE}"


# Public alias for modules that referenced the unqualified-column + COALESCE form.
CONTACTO_GMAIL_SOURCE_SQL = sql_predicate_contacto_gmail_source(coalesce_null=True)
