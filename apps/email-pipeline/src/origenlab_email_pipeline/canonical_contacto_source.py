"""Canonical vs legacy email ``source_file`` tiers (re-export hub).

Prefer importing operational constants and :func:`classify_email_source` from this module in new
code; implementation remains in :mod:`origenlab_email_pipeline.contacto_gmail_source` to
preserve a single source of truth for SQL predicates.
"""

from __future__ import annotations

from origenlab_email_pipeline.contacto_gmail_source import (
    CONTACTO_GMAIL_LIKE,
    CONTACTO_GMAIL_SOURCE_PREFIX,
    CONTACTO_GMAIL_SOURCE_SQL,
    CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE,
    EmailSourceTier,
    LEGACY_LABDELIVERY_SOURCE_LIKE,
    canonical_contacto_where_clause,
    classify_email_source,
    is_canonical_contacto_gmail_source,
    sql_predicate_contacto_gmail_source,
)

__all__ = [
    "CONTACTO_GMAIL_LIKE",
    "CONTACTO_GMAIL_SOURCE_PREFIX",
    "CONTACTO_GMAIL_SOURCE_SQL",
    "CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE",
    "EmailSourceTier",
    "LEGACY_LABDELIVERY_SOURCE_LIKE",
    "canonical_contacto_where_clause",
    "classify_email_source",
    "is_canonical_contacto_gmail_source",
    "sql_predicate_contacto_gmail_source",
]
