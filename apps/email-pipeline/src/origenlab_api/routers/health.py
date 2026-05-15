"""Health endpoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from origenlab_api.db import PostgresUnavailableError, postgres_connection
from origenlab_api.deps import get_postgres_url, get_settings_dict
from origenlab_api.schemas import (
    DependencyStatus,
    HealthDependenciesResponse,
    HealthResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/dependencies", response_model=HealthDependenciesResponse)
def health_dependencies(
    settings: Annotated[dict[str, str | bool], Depends(get_settings_dict)],
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> HealthDependenciesResponse:
    deps: list[DependencyStatus] = []

    try:
        with postgres_connection(postgres_url) as conn:
            conn.execute("SELECT 1")
        deps.append(DependencyStatus(name="postgres", status="ok", detail="connected"))
        pg_status: str = "ok"
    except PostgresUnavailableError as exc:
        deps.append(DependencyStatus(name="postgres", status="error", detail=str(exc)))
        pg_status = "error"
    except Exception as exc:
        deps.append(DependencyStatus(name="postgres", status="error", detail=str(exc)))
        pg_status = "error"

    sqlite_path = Path(str(settings["sqlite_path"]))
    if sqlite_path.is_file():
        try:
            uri = f"file:{sqlite_path.resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.execute("PRAGMA query_only=ON")
            conn.execute("SELECT 1")
            conn.close()
            deps.append(
                DependencyStatus(
                    name="sqlite",
                    status="ok",
                    detail="read-only ping (not used for API data in v1)",
                )
            )
        except Exception as exc:
            deps.append(
                DependencyStatus(name="sqlite", status="error", detail=str(exc))
            )
    else:
        deps.append(
            DependencyStatus(
                name="sqlite",
                status="skipped",
                detail=f"file not found: {sqlite_path}",
            )
        )

    if pg_status == "error":
        overall = "error"
    elif any(d.status == "error" for d in deps if d.name != "postgres"):
        overall = "degraded"
    else:
        overall = "ok"

    return HealthDependenciesResponse(
        status=overall,  # type: ignore[arg-type]
        dependencies=deps,
        postgres_url_redacted=str(settings.get("postgres_url_redacted", "")),
    )
