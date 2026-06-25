"""Operator status response (JSON-safe subset)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PathInfo(BaseModel):
    """Redacted path metadata safe for API responses and OpenAPI docs."""

    redacted: bool = True
    basename: str = ""
    kind: Literal["file", "directory", "unknown"] = "unknown"


class DailyCoreRunStatus(BaseModel):
    """Latest daily-core manifest summary with a typed public contract.

    The source manifest can evolve, so extra keys remain accepted for backward
    compatibility while Swagger documents the stable fields used by the
    dashboard and portfolio demo.
    """

    model_config = ConfigDict(extra="allow")

    path: str = ""
    exists: bool = False
    loaded: bool = False
    schema_version: int | None = None
    workflow: str | None = None
    generated_at_utc: str | None = None
    status: str | None = None
    returncode: int | None = None
    step_count: int | None = None
    last_step: str | None = None
    send_approval: bool | None = False
    postgres_mirror: str | None = None


class OperatorStatusResponse(BaseModel):
    verdict: str
    sqlite_path: str
    sqlite_path_info: PathInfo | None = None
    campaign_mode: str | None = None
    operator_focus: str | None = None
    outbound_readiness: str
    warnings: list[str] = Field(default_factory=list)
    daily_core_run: DailyCoreRunStatus = Field(default_factory=DailyCoreRunStatus)
