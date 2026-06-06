"""Operator status response (JSON-safe subset)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OperatorStatusResponse(BaseModel):
    verdict: str
    sqlite_path: str
    campaign_mode: str | None = None
    operator_focus: str | None = None
    outbound_readiness: str
    warnings: list[str] = Field(default_factory=list)
    daily_core_run: dict[str, Any] = Field(default_factory=dict)
