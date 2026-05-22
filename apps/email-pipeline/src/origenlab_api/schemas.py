"""Pydantic response models for API v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    COMMERCIAL_PURCHASE_DISCLAIMER,
    POSTGRES_MIRROR_NOTE,
    ClassificationActionGroup,
    ClassificationActionsResponse,
    ClassificationEmailRow,
    ClassificationRecentResponse,
    ClassificationSummaryResponse,
    CommercialPurchaseEventDetailResponse,
    CommercialPurchaseEventItemRow,
    CommercialPurchaseEventRow,
    CommercialPurchaseEventsListResponse,
    ContactRow,
    DashboardSummaryResponse,
    DashboardSyncMetaResponse,
    DependencyStatus,
    EmailSuppressionRow,
    HealthDependenciesResponse,
    OrganizationRow,
    OutreachContactStateRow,
    OutboundReadinessResponse,
    PaginatedContactsResponse,
    PaginatedEmailSuppressionsResponse,
    PaginatedOrganizationsResponse,
    PaginatedOutreachStateResponse,
)

__all__ = [
    "COMMERCIAL_PURCHASE_DISCLAIMER",
    "POSTGRES_MIRROR_NOTE",
    "ClassificationActionGroup",
    "ClassificationActionsResponse",
    "ClassificationEmailRow",
    "ClassificationRecentResponse",
    "ClassificationSummaryResponse",
    "CommercialPurchaseEventDetailResponse",
    "CommercialPurchaseEventItemRow",
    "CommercialPurchaseEventRow",
    "CommercialPurchaseEventsListResponse",
    "ContactRow",
    "DashboardSummaryResponse",
    "DashboardSyncMetaResponse",
    "DependencyStatus",
    "EmailSuppressionRow",
    "HealthDependenciesResponse",
    "OrganizationRow",
    "OutreachContactStateRow",
    "OutboundReadinessResponse",
    "PaginatedContactsResponse",
    "PaginatedEmailSuppressionsResponse",
    "PaginatedOrganizationsResponse",
    "PaginatedOutreachStateResponse",
]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "origenlab-api"
    api_version: str = "v1"
    read_only: bool = True
