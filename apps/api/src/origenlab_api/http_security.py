"""Production HTTP hardening (CORS, OpenAPI docs, response headers) for read-only operator API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from origenlab_api.settings import Settings

_OPERATOR_CACHE_CONTROL = "no-store, private"
_SECURITY_RESPONSE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Cache-Control": _OPERATOR_CACHE_CONTROL,
}


class OperatorSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline headers for JSON operator responses (no full CSP on API)."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for key, value in _SECURITY_RESPONSE_HEADERS.items():
            if key not in response.headers:
                response.headers[key] = value
        return response


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
    app.add_middleware(OperatorSecurityHeadersMiddleware)
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
