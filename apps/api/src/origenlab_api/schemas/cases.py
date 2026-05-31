"""Warm commercial case queue (read-only previews)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WarmCaseCategory = Literal[
    "client_opportunity",
    "client_response",
    "supplier_quote_received",
    "supplier_followup",
    "payment_admin",
    "logistics_admin",
    "internal_admin",
    "system_noise",
    "bounce_problem",
    "deal_evidence_candidate",
    "quote_sent",
    "waiting_supplier",
    "waiting_client",
    "campaign_outreach",
    "waiting_campaign_reply",
    "auto_acknowledgement",
    # Legacy aliases (mirror/promotion rows until fully migrated)
    "client_reply",
    "supplier_reply",
    "bounce",
    "opportunity",
    "auto_reply",
    "vendor_logistics",
]

WarmCaseStatus = Literal["new", "open", "waiting", "quoted", "problem"]

WARM_CASE_CATEGORIES: frozenset[str] = frozenset(
    {
        "client_opportunity",
        "client_response",
        "supplier_quote_received",
        "supplier_followup",
        "payment_admin",
        "logistics_admin",
        "internal_admin",
        "system_noise",
        "bounce_problem",
        "deal_evidence_candidate",
        "quote_sent",
        "waiting_supplier",
        "waiting_client",
        "campaign_outreach",
        "waiting_campaign_reply",
        "auto_acknowledgement",
        "client_reply",
        "supplier_reply",
        "bounce",
        "opportunity",
        "auto_reply",
        "vendor_logistics",
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
    grouped_email_count: int = 1


class WarmCasesResponse(BaseModel):
    meta: WarmCasesMeta
    items: list[WarmCaseItem] = Field(default_factory=list)
