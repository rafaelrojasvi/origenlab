"""Production HTTP hardening (CORS, OpenAPI docs) for read-only operator API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from origenlab_api.settings import Settings


def openapi_docs_enabled(settings: Settings) -> bool:
    if settings.api_disable_docs:
        return False
    if settings.production_mode():
        return False
    return True


def validate_http_security_settings(settings: Settings) -> None:
    """Fail fast on unsafe production CORS configuration."""
    for origin in settings.parsed_cors_origins():
        if origin == "*":
            raise ValueError(
                "ORIGENLAB_API_CORS_ORIGINS must not include '*' in production "
                "(list explicit dashboard origins only)"
            )
        if not origin.startswith(("https://", "http://")):
            raise ValueError(
                f"Invalid CORS origin {origin!r}: must start with http:// or https://"
            )


def configure_http_security(app: FastAPI, settings: Settings) -> None:
    validate_http_security_settings(settings)
    origins = settings.parsed_cors_origins()
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[],
    )
