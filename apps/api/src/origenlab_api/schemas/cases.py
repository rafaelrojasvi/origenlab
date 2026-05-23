"""Warm commercial case queue (read-only previews)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WarmCaseCategory = Literal[
    "client_reply",
    "supplier_reply",
    "quote_sent",
    "waiting_supplier",
    "waiting_client",
    "bounce",
    "opportunity",
    "auto_reply",
    "vendor_logistics",
    "payment_admin",
]

WarmCaseStatus = Literal["new", "open", "waiting", "quoted", "problem"]

WARM_CASE_CATEGORIES: frozenset[str] = frozenset(
    {
        "client_reply",
        "supplier_reply",
        "quote_sent",
        "waiting_supplier",
        "waiting_client",
        "bounce",
        "opportunity",
        "auto_reply",
        "vendor_logistics",
        "payment_admin",
    }
)


class WarmCasesMeta(BaseModel):
    data_source: Literal["sqlite", "postgres_mirror"] = "sqlite"
    read_only: bool = True
    reduced_mode: bool = False
    count: int = 0
    enrichment_available: bool = False
    note: str = ""


class WarmCaseItem(BaseModel):
    case_id: str
    last_email_id: int
    last_seen_at: str | None = None
    account_name: str = ""
    contact_email: str = ""
    subject: str = ""
    category: WarmCaseCategory
    status: WarmCaseStatus
    next_action: str = ""
    equipment_signal: str = ""
    snippet: str = ""
    gmail_url: str | None = None


class WarmCasesResponse(BaseModel):
    meta: WarmCasesMeta
    items: list[WarmCaseItem] = Field(default_factory=list)
