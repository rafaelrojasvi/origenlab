"""Health dependency checks for Postgres dashboard mirror API."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.postgres_dashboard_api.db import (
    PostgresUnavailableError,
    postgres_connection,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    DependencyStatus,
    HealthDependenciesResponse,
)


def _configured_marker(value: str) -> str:
    return "<configured>" if str(value or "").strip() else "<not configured>"


def build_health_dependencies_response(
    *,
    postgres_url: str,
    postgres_url_redacted: str,
    sqlite_path: Path,
) -> HealthDependenciesResponse:
    """Build demo-safe dependency health without leaking infra URLs or local paths."""
    deps: list[DependencyStatus] = []
    _ = postgres_url_redacted  # kept for shared API compatibility; response uses a safer marker.

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
                detail="sqlite file not configured or not found",
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
        postgres_url_redacted=_configured_marker(postgres_url),
    )
