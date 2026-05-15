"""Postgres access helpers (read-only)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Iterator

try:
    import psycopg
    from psycopg import Connection
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    Connection = Any  # type: ignore[misc, assignment]
    dict_row = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None


class PostgresUnavailableError(RuntimeError):
    """psycopg not installed or connection failed."""


def require_psycopg() -> None:
    if psycopg is None:
        raise PostgresUnavailableError(
            f"psycopg required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


@contextmanager
def postgres_connection(url: str) -> Generator[Connection, None, None]:
    require_psycopg()
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def table_exists(conn: Connection, *, schema: str, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1
        """,
        (schema, table),
    ).fetchone()
    return bool(row)


def safe_count(conn: Connection, *, schema: str, table: str) -> tuple[bool, int]:
    """Return (table_exists, row_count). Missing table → (False, 0)."""
    if not table_exists(conn, schema=schema, table=table):
        return False, 0
    qualified = f"{schema}.{table}"
    row = conn.execute(f"SELECT COUNT(*)::bigint AS n FROM {qualified}").fetchone()
    return True, int((row or {}).get("n") or 0)


def fetch_all(conn: Connection, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params or ())
    return list(cur.fetchall())


def fetch_one(conn: Connection, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    row = conn.execute(sql, params or ()).fetchone()
    return dict(row) if row else None
