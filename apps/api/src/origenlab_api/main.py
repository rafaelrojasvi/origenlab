"""FastAPI application (API-0: operator plane, read-only)."""

from __future__ import annotations

from fastapi import FastAPI

from origenlab_api.backends.factory import validate_api_settings
from origenlab_api.routes import cases, contacts, emails, health, operator, opportunities
from origenlab_api.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="OrigenLab API",
        description=(
            "Read-only operator API (SQLite-first). "
            "Does not send email, ingest Gmail, or write SQLite/Postgres. "
            "email-pipeline scripts remain the mutation path."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.include_router(health.router)
    app.include_router(operator.router)
    app.include_router(emails.router)
    app.include_router(cases.router)
    app.include_router(opportunities.router)
    app.include_router(contacts.router)
    validate_api_settings(get_settings())
    return app


app = create_app()
