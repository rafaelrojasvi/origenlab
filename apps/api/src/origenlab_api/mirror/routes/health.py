"""Mirror health endpoints (Postgres dependency checks)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from origenlab_api.mirror.deps import mirror_postgres_url_redacted, resolve_mirror_postgres_url
from origenlab_api.settings import Settings, get_settings
from origenlab_email_pipeline.postgres_dashboard_api.health import (
    build_health_dependencies_response,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import HealthDependenciesResponse

router = APIRouter(tags=["postgres-mirror"])


@router.get("/dependencies", response_model=HealthDependenciesResponse)
def mirror_health_dependencies(
    settings: Settings = Depends(get_settings),
) -> HealthDependenciesResponse:
    """Postgres + optional SQLite reachability (legacy /health/dependencies parity)."""
    return build_health_dependencies_response(
        postgres_url=resolve_mirror_postgres_url(settings),
        postgres_url_redacted=mirror_postgres_url_redacted(settings),
        sqlite_path=settings.resolved_sqlite_path(),
    )
