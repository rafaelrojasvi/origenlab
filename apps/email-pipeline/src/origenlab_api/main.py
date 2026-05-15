"""FastAPI application factory (read-only API v1)."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from origenlab_api.routers import contacts, dashboard, health, organizations, outbound

_DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
)


def _cors_origins() -> list[str]:
    raw = (os.environ.get("ORIGENLAB_API_CORS_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_CORS_ORIGINS)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(contacts.router)
    app.include_router(organizations.router)
    app.include_router(outbound.router)
    return app


app = create_app()
