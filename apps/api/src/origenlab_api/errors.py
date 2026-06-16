"""Centralized safe JSON error responses for apps/api."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from origenlab_api.schemas.errors import ApiErrorBody, ApiErrorResponse

_POSTGRES_URL_RE = re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE)
_ENV_SECRET_RE = re.compile(
    r"(ORIGENLAB_POSTGRES_URL|ALEMBIC_DATABASE_URL|CHILECOMPRA_API_TICKET)=\S+",
    re.IGNORECASE,
)
_PASSWORD_KV_RE = re.compile(r"(password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE)

_FORBIDDEN_SUBSTRINGS = (
    "traceback",
    "Traceback",
)


def sanitize_text(text: str) -> str:
    """Redact secrets and connection strings from operator-facing error text."""
    if not text:
        return ""
    cleaned = text
    cleaned = _POSTGRES_URL_RE.sub("<redacted-database-url>", cleaned)
    cleaned = _ENV_SECRET_RE.sub(r"\1=<redacted>", cleaned)
    cleaned = _PASSWORD_KV_RE.sub(r"\1=<redacted>", cleaned)
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in cleaned:
            return "An error occurred"
    return cleaned


def _error_payload(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    body = ApiErrorResponse(
        error=ApiErrorBody(
            code=code,
            message=sanitize_text(message),
            details=details or {},
            request_id=request_id,
        )
    )
    return body.model_dump()


def json_error_response(
    status_code: int,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_error_payload(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        ),
    )


def _string_detail(exc: StarletteHTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("msg")
        if isinstance(message, str):
            return message
        return sanitize_text(str(detail))
    if isinstance(detail, list):
        parts = [str(item) for item in detail[:3]]
        return "; ".join(parts) if parts else "Request failed"
    return "Request failed"


def _code_for_http_exception(exc: StarletteHTTPException, message: str) -> str:
    status = exc.status_code
    lowered = message.lower()
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 503:
        if "mirror" in lowered or "postgres url required" in lowered or "origenlab_postgres_url" in lowered:
            return "mirror_not_configured"
        return "backend_unavailable"
    if status == 422 and "invalid category" in lowered:
        return "invalid_query_param"
    if status in {400, 422}:
        return "validation_error"
    if status >= 500:
        return "internal_error"
    return "validation_error"


def _details_for_http_exception(exc: StarletteHTTPException, message: str) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if exc.status_code == 422 and "invalid category" in message.lower():
        details["param"] = "category"
        if "allowed:" in message:
            details["hint"] = sanitize_text(message.split("allowed:", 1)[1].strip())
    detail = exc.detail
    if isinstance(detail, dict):
        details.update({k: sanitize_text(str(v)) if isinstance(v, str) else v for k, v in detail.items()})
    return details


def _validation_details(exc: RequestValidationError) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for item in exc.errors():
        errors.append(
            {
                "loc": [str(part) for part in item.get("loc", ())],
                "msg": sanitize_text(str(item.get("msg", ""))),
                "type": str(item.get("type", "")),
            }
        )
    return {"validation_errors": errors}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        message = _string_detail(exc)
        code = _code_for_http_exception(exc, message)
        return json_error_response(
            exc.status_code,
            code=code,
            message=message,
            details=_details_for_http_exception(exc, message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return json_error_response(
            422,
            code="validation_error",
            message="Request validation failed",
            details=_validation_details(exc),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return json_error_response(
            500,
            code="internal_error",
            message="An unexpected error occurred",
            details={},
        )
