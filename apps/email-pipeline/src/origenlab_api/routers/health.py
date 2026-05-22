"""Health endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from origenlab_api.deps import get_postgres_url, get_settings_dict
from origenlab_api.schemas import HealthDependenciesResponse, HealthResponse
from origenlab_email_pipeline.postgres_dashboard_api.health import (
    build_health_dependencies_response,
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
    from pathlib import Path

    return build_health_dependencies_response(
        postgres_url=postgres_url,
        postgres_url_redacted=str(settings.get("postgres_url_redacted", "")),
        sqlite_path=Path(str(settings["sqlite_path"])),
    )
