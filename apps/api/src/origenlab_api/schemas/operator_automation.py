"""Operator automation status response (read-only local state)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CronNote(BaseModel):
    note: str


class OperatorAutomationStatusResponse(BaseModel):
    generated_at_utc: str
    active_current_dir: str
    verdict: str
    daily_core: dict[str, Any] = Field(default_factory=dict)
    mail_auto_refresh: dict[str, Any] = Field(default_factory=dict)
    dashboard_auto_mirror: dict[str, Any] = Field(default_factory=dict)
    chilecompra_equipment_auto_refresh: dict[str, Any] = Field(default_factory=dict)
    cron: CronNote = Field(default_factory=lambda: CronNote(note="not inspected by this command"))
    recommended_action: str
    warnings: list[str] = Field(default_factory=list)
    source: str | None = None
    snapshot_updated_at: str | None = None
    snapshot_stale: bool | None = None
