"""Pydantic response models for API v1."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "origenlab-api"
    api_version: str = "v1"
    read_only: bool = True


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "error", "skipped"]
    detail: str = ""


class HealthDependenciesResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    dependencies: list[DependencyStatus]
    postgres_url_redacted: str = ""
    note: str = (
        "API reads Postgres mirrors only. SQLite ingest remains authoritative until cutover."
    )


class DashboardSummaryResponse(BaseModel):
    contact_count: int = 0
    organization_count: int = 0
    opportunity_signal_count: int = 0
    email_suppression_count: int = 0
    domain_suppression_count: int = 0
    outreach_state_count: int = 0
    tables: dict[str, bool] = Field(default_factory=dict)
    data_source: Literal["postgres_mirror"] = "postgres_mirror"
    eventually_consistent: bool = True
    scope: Literal["canonical", "archive"] = "canonical"
    scope_available: bool = True
    scope_note: str = ""
    archive_mirror_counts: dict[str, int] = Field(default_factory=dict)


class ContactRow(BaseModel):
    email: str
    contact_name_best: str | None = None
    domain: str | None = None
    organization_name_guess: str | None = None
    organization_type_guess: str | None = None
    first_seen_at: datetime | str | None = None
    last_seen_at: datetime | str | None = None
    total_emails: int | None = None
    confidence_score: float | None = None
    top_equipment_tags: str | None = None


class OrganizationRow(BaseModel):
    domain: str
    organization_name_guess: str | None = None
    organization_type_guess: str | None = None
    first_seen_at: datetime | str | None = None
    last_seen_at: datetime | str | None = None
    total_emails: int | None = None
    total_contacts: int | None = None
    top_equipment_tags: str | None = None
    key_contacts: str | None = None


class PaginatedContactsResponse(BaseModel):
    items: list[ContactRow]
    total: int
    limit: int
    offset: int
    table_available: bool = True
    scope: Literal["canonical", "archive"] = "canonical"
    scope_available: bool = True
    scope_note: str = ""


class PaginatedOrganizationsResponse(BaseModel):
    items: list[OrganizationRow]
    total: int
    limit: int
    offset: int
    table_available: bool = True
    scope: Literal["canonical", "archive"] = "canonical"
    scope_available: bool = True
    scope_note: str = ""


class EmailSuppressionRow(BaseModel):
    email: str
    suppression_reason_code: str
    suppression_reason_text: str | None = None
    suppression_source: str | None = None
    last_bounced_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    updated_by: str | None = None


class PaginatedEmailSuppressionsResponse(BaseModel):
    items: list[EmailSuppressionRow]
    total: int
    limit: int
    offset: int
    table_available: bool = True


class OutreachContactStateRow(BaseModel):
    contact_email_norm: str
    state: str
    first_contacted_at: datetime | str | None = None
    last_contacted_at: datetime | str | None = None
    source: str | None = None
    notes: str | None = None
    updated_at: datetime | str | None = None
    updated_by: str | None = None
    lead_id: int | None = None


class PaginatedOutreachStateResponse(BaseModel):
    items: list[OutreachContactStateRow]
    total: int
    limit: int
    offset: int
    table_available: bool = True


class OutboundReadinessResponse(BaseModel):
    verdict: Literal["ready", "ready_with_warnings", "not_ready", "unknown"]
    data_source: Literal["postgres_mirror"] = "postgres_mirror"
    eventually_consistent: bool = True
    postgres_url_redacted: str = ""
    gmail_user: str = ""
    tables: dict[str, bool] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    mart: dict[str, Any] = Field(default_factory=dict)
    sidecars: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Based on Postgres mirror tables only. Sent-folder ingest and live gates still use "
        "SQLite; sync lag may make this differ from Streamlit/CLI truth."
    )
