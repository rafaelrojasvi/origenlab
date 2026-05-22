"""Postgres access helpers (read-only)."""

from __future__ import annotations

from origenlab_email_pipeline.postgres_dashboard_api.db import (
    PostgresUnavailableError,
    fetch_all,
    fetch_one,
    postgres_connection,
    require_psycopg,
    safe_count,
    table_exists,
)

__all__ = [
    "PostgresUnavailableError",
    "fetch_all",
    "fetch_one",
    "postgres_connection",
    "require_psycopg",
    "safe_count",
    "table_exists",
]
