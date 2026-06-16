"""Request correlation IDs for operator API responses."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LEN = 128
_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_\-.:]{1,128}$")


def is_safe_request_id(value: str) -> bool:
    text = (value or "").strip()
    if not text or len(text) > _MAX_REQUEST_ID_LEN:
        return False
    return _SAFE_REQUEST_ID_RE.fullmatch(text) is not None


def resolve_request_id(request: Request) -> str:
    """Reuse a safe incoming X-Request-ID or generate a new correlation id."""
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing

    incoming = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
    request_id = incoming if is_safe_request_id(incoming) else uuid4().hex
    request.state.request_id = request_id
    return request_id


def get_request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    if isinstance(value, str) and value:
        return value
    return None


def attach_request_id_header(response: Response, request_id: str | None) -> None:
    if request_id:
        response.headers[REQUEST_ID_HEADER] = request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign request.state.request_id and echo it on every response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = resolve_request_id(request)
        response = await call_next(request)
        attach_request_id_header(response, request_id)
        return response
