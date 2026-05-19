"""Contact intelligence (read-only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContactMeta(BaseModel):
    data_source: Literal["sqlite"] = "sqlite"
    read_only: bool = True
    reduced_mode: bool = False
    note: str = ""


class ContactProfile(BaseModel):
    email: str = ""
    normalized_email: str = ""
    name: str = ""
    domain: str = ""
    organization_name: str = ""
    organization_domain: str = ""
    last_seen_at: str | None = None
    first_seen_at: str | None = None
    message_count: int = 0


class ContactOutreach(BaseModel):
    state: str | None = None
    last_contacted_at: str | None = None
    source: str | None = None
    updated_by: str | None = None
    notes: str | None = None
    do_not_repeat: bool = False
    suppressed_email: bool = False
    suppressed_domain: bool = False


class ContactSentHistory(BaseModel):
    sent_count: int = 0
    latest_sent_at: str | None = None
    latest_subject: str | None = None


class ContactDetailResponse(BaseModel):
    meta: ContactMeta
    contact: ContactProfile
    outreach: ContactOutreach
    sent_history: ContactSentHistory
    warnings: list[str] = Field(default_factory=list)
