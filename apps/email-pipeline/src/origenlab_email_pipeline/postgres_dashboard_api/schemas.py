"""Pydantic models for Postgres dashboard mirror endpoints (API-3 shared)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

POSTGRES_MIRROR_NOTE: str = (
    "Espejo Postgres de solo lectura; SQLite/Gmail sigue siendo la fuente operativa. "
    "Los correos nuevos no aparecen aquí hasta ingest Gmail, rebuild del mart y sync del espejo."
)


class DashboardSummaryResponse(BaseModel):
    contact_count: int = 0
    organization_count: int = 0
    opportunity_signal_count: int = 0
    email_suppression_count: int = 0
    domain_suppression_count: int = 0
    outreach_state_count: int = 0
    commercial_purchase_event_count: int = 0
    commercial_purchase_event_item_count: int = 0
    latest_confirmed_purchase_gross_clp: int | None = None
    tables: dict[str, bool] = Field(default_factory=dict)
    data_source: Literal["postgres_mirror"] = "postgres_mirror"
    eventually_consistent: bool = True
    scope: Literal["canonical", "archive"] = "canonical"
    scope_available: bool = True
    scope_note: str = ""
    archive_mirror_counts: dict[str, int] = Field(default_factory=dict)


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


class ClassificationSummaryResponse(BaseModel):
    scope: Literal["canonical"] = "canonical"
    table_available: bool = False
    status: Literal["missing_table", "no_rows", "ok"] = "no_rows"
    total_rows: int = 0
    counts_by_label: dict[str, int] = Field(default_factory=dict)
    kpi: dict[str, int] = Field(default_factory=dict)
    disclaimer: str = (
        "Clasificación heurística de QA sobre Gmail canónico (contacto@origenlab.cl). "
        "No es verdad CRM ni decisión automática de envío."
    )


class ClassificationEmailRow(BaseModel):
    email_id: int
    date_iso: datetime | str | None = None
    folder: str | None = None
    from_addr: str | None = None
    to_addrs: str | None = None
    subject: str | None = None
    predicted_label: str
    confidence: str
    ambiguous: bool = False
    recommended_action: str
    etiqueta_ui: str
    evidence: str | None = None
    contact_email: str | None = None
    contact_domain: str | None = None


class ClassificationRecentResponse(BaseModel):
    scope: Literal["canonical"] = "canonical"
    table_available: bool = False
    items: list[ClassificationEmailRow] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    label_filter: str | None = None


class ClassificationActionGroup(BaseModel):
    recommended_action: str
    action_label_es: str
    count: int
    sample_subjects: list[str] = Field(default_factory=list)


class ClassificationActionsResponse(BaseModel):
    scope: Literal["canonical"] = "canonical"
    table_available: bool = False
    groups: list[ClassificationActionGroup] = Field(default_factory=list)
    disclaimer: str = (
        "Acciones sugeridas por heurística; el operador decide en Streamlit/CLI."
    )


class CommercialPurchaseEventItemRow(BaseModel):
    line_number: int
    ref_code: str | None = None
    product_name: str
    brand: str | None = None
    quantity: str | None = None
    net_amount_clp: int | None = None
    evidence_source: str | None = None


class CommercialPurchaseEventRow(BaseModel):
    id: int
    source_email_id: int | None = None
    buyer_org_name: str
    buyer_contact_name: str | None = None
    buyer_contact_email: str | None = None
    buyer_domain: str | None = None
    purchase_status: str
    purchase_status_label_es: str = ""
    oc_number: str
    quote_number: str | None = None
    project_name: str | None = None
    project_code: str | None = None
    net_amount_clp: int | None = None
    iva_amount_clp: int | None = None
    gross_amount_clp: int | None = None
    currency: str = "CLP"
    email_date_iso: str | None = None
    email_subject: str | None = None
    commercial_summary: str | None = None
    suggested_action_es: str | None = None
    line_items: list[CommercialPurchaseEventItemRow] = Field(default_factory=list)
    product_summary: str | None = None


COMMERCIAL_PURCHASE_DISCLAIMER: str = (
    "Eventos de compra confirmados promovidos desde Gmail/SQLite. "
    "No sustituyen revisión operativa de OC, factura o despacho."
)


class CommercialPurchaseEventsListResponse(BaseModel):
    table_available: bool = False
    items: list[CommercialPurchaseEventRow] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    disclaimer: str = COMMERCIAL_PURCHASE_DISCLAIMER


class CommercialPurchaseEventDetailResponse(BaseModel):
    table_available: bool = False
    event: CommercialPurchaseEventRow | None = None
    disclaimer: str = COMMERCIAL_PURCHASE_DISCLAIMER


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


class DashboardSyncMetaResponse(BaseModel):
    """Latest dashboard Postgres mirror sync (reporting.dashboard_sync_run)."""

    table_available: bool = False
    status: Literal[
        "missing_table", "no_rows", "success", "failed", "dry_run", "unknown"
    ] = "no_rows"
    latest_sync_id: int | None = None
    started_at: datetime | str | None = None
    finished_at: datetime | str | None = None
    elapsed_seconds: float | None = None
    postgres_mirror_note: str = POSTGRES_MIRROR_NOTE
    canonical_contact_count: int = 0
    canonical_organization_count: int = 0
    canonical_opportunity_signal_count: int = 0
    archive_contact_count: int = 0
    archive_organization_count: int = 0
    archive_opportunity_signal_count: int = 0
    email_suppression_count: int = 0
    domain_suppression_count: int = 0
    outreach_state_count: int = 0
    error_message: str | None = None


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
