"""Health check."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from origenlab_api.schemas.health import HealthResponse
from origenlab_api.services.health_service import build_health_response
from origenlab_api.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return build_health_response(settings)
