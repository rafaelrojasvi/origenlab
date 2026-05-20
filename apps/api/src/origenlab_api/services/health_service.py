"""Health response builder."""

from __future__ import annotations

from origenlab_api.schemas.health import HealthResponse
from origenlab_api.settings import Settings


def build_health_response(settings: Settings) -> HealthResponse:
    backend = settings.resolved_api_backend()
    postgres_configured = settings.postgres_configured()
    if backend == "postgres":
        mode = "operator-postgres-mirror-readonly"
    else:
        mode = "operator-sqlite-readonly"
    return HealthResponse(
        ok=True,
        service="origenlab-api",
        mode=mode,
        backend=backend,
        postgres_configured=postgres_configured,
    )
