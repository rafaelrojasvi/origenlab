"""Health check."""

from __future__ import annotations

from fastapi import APIRouter

from origenlab_api.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
