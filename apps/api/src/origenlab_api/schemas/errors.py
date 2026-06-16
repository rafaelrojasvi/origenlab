"""Unified API error envelope (read-only operator API)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody
