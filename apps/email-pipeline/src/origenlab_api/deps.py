"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from psycopg import Connection

from origenlab_api.config import ApiConfigError, get_api_settings
from origenlab_api.db import PostgresUnavailableError, postgres_connection


def get_settings_dict() -> dict[str, str | bool]:
    try:
        return get_api_settings()
    except ApiConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_postgres_url(
    settings: Annotated[dict[str, str | bool], Depends(get_settings_dict)],
) -> str:
    return str(settings["postgres_url"])


def get_db_conn(
    request: Request,
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> Generator[Connection, None, None]:
    """Yield a read-only Postgres connection (one per request)."""
    try:
        with postgres_connection(postgres_url) as conn:
            request.state.db_conn = conn
            yield conn
    except PostgresUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Postgres connection failed: {exc}",
        ) from exc


DbConn = Annotated[Connection, Depends(get_db_conn)]
