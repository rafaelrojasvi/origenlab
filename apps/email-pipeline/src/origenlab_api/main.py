"""FastAPI application factory (read-only API v1)."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from origenlab_api.routers import (
    classification,
    contacts,
    dashboard,
    health,
    meta,
    organizations,
    outbound,
)

# Local React dashboard (Vite). Override: ORIGENLAB_API_CORS_ORIGINS=comma-separated list.
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
)


def cors_origins() -> list[str]:
    """Resolved allowlist for CORSMiddleware (env or defaults)."""
    raw = (os.environ.get("ORIGENLAB_API_CORS_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(DEFAULT_CORS_ORIGINS)


def _install_cors(app: FastAPI) -> None:
    """Register CORS before route handlers (middleware wraps the app outermost)."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
    )


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(meta.router)
    app.include_router(classification.router)
    app.include_router(dashboard.router)
    app.include_router(contacts.router)
    app.include_router(organizations.router)
    app.include_router(outbound.router)


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
    _install_cors(app)
    _register_routers(app)
    return app


app = create_app()
