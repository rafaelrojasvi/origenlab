"""Recent emails (canonical Gmail contacto) — read-only previews."""

from __future__ import annotations

from pydantic import BaseModel, Field

from origenlab_api.schemas.common import ResponseMeta


class EmailRecentRow(BaseModel):
    email_id: int
    date_iso: str | None = None
    subject_preview: str = ""
    sender_preview: str = ""
    source_file: str | None = None
    folder_hint: str | None = None
    has_positive_signal: bool = False
    has_suppression_signal: bool = False


class EmailsRecentResponse(BaseModel):
    meta: ResponseMeta
    items: list[EmailRecentRow] = Field(default_factory=list)
    total_returned: int = 0
    days_window: int = 7
    scope_note: str = ""
    enrichment_available: bool = False
    reduced_mode: bool = False
