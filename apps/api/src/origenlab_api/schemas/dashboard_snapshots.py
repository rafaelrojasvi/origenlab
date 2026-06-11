"""Dashboard snapshot API response shapes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SnapshotSource = Literal["postgres_snapshot", "filesystem_active_current"]


class GmailInteractionAuditDomainRow(BaseModel):
    domain: str
    message_count: int = 0
    sent_count: int = 0
    received_count: int = 0
    thread_count: int = 0
    latest_email_at: str | None = None
    latest_subject_safe: str = ""
    has_attachments: bool = False
    matched_aliases: list[str] = Field(default_factory=list)


class GmailInteractionAuditSnapshot(BaseModel):
    schema_version: int = 1
    generated_at_utc: str
    source: str
    lookback_days: int
    domains: list[GmailInteractionAuditDomainRow] = Field(default_factory=list)


class GmailInteractionAuditResponse(BaseModel):
    status: Literal["ok", "snapshot_missing"]
    message: str
    snapshot: GmailInteractionAuditSnapshot | None = None
    updated_at: str | None = None
    source: SnapshotSource | None = None
    snapshot_stale: bool | None = None
    read_only: bool = True
