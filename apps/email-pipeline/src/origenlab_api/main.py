"""FastAPI application factory (read-only API v1)."""

from __future__ import annotations

from fastapi import FastAPI

from origenlab_api.routers import contacts, dashboard, health, organizations, outbound


def create_app() -> FastAPI:
    app = FastAPI(
        title="OrigenLab Commercial Dashboard API",
        description=(
            "Read-only API over PostgreSQL mirrors (Slice 1). "
            "Does not send email, mutate SQLite, or trigger ingest/rebuild jobs."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(contacts.router)
    app.include_router(organizations.router)
    app.include_router(outbound.router)
    return app


app = create_app()
