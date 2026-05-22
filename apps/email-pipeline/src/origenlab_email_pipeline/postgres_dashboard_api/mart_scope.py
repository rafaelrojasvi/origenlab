"""Mart relation resolution for canonical vs archive Postgres mirror scope."""

from __future__ import annotations

from psycopg import Connection

from origenlab_email_pipeline.operational_scope import (
    ARCHIVE_SCOPE_NOTE,
    CANONICAL_POSTGRES_UNAVAILABLE_NOTE,
    CANONICAL_SCOPE_NOTE,
    DataScope,
    postgres_mart_relation,
)

from origenlab_email_pipeline.postgres_dashboard_api.db import table_exists


def mart_base_table(relation: str) -> str:
    return relation.split(".", 1)[1]


def resolve_mart_scope(
    conn: Connection,
    *,
    base: str,
    scope: DataScope,
) -> tuple[str, bool, str]:
    """Return (fully-qualified relation, scope_available, scope_note)."""
    if scope == "archive":
        rel = postgres_mart_relation(base, "archive")
        exists = table_exists(conn, schema="mart", table=mart_base_table(rel))
        return rel, exists, ARCHIVE_SCOPE_NOTE
    rel = postgres_mart_relation(base, "canonical")
    exists = table_exists(conn, schema="mart", table=mart_base_table(rel))
    if exists:
        return rel, True, CANONICAL_SCOPE_NOTE
    return rel, False, CANONICAL_POSTGRES_UNAVAILABLE_NOTE
