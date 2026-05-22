"""Shared read-only Postgres dashboard mirror queries and schemas (API-3).

Consumed by ``apps/api`` ``GET /mirror/*`` routes on port **8001** (legacy
email-pipeline FastAPI on :8000 was removed in API-3 Phase 6).
"""

from origenlab_email_pipeline.postgres_dashboard_api.classification import (
    classification_actions,
    classification_recent,
    classification_summary,
)
from origenlab_email_pipeline.postgres_dashboard_api.commercial_purchase import (
    get_commercial_purchase_event,
    list_commercial_purchase_events,
)
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import (
    list_email_suppressions,
    list_outreach_contact_state,
)
from origenlab_email_pipeline.postgres_dashboard_api.outbound_readiness import (
    assess_postgres_outbound_readiness,
)
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
    DashboardSummaryResponse,
    DashboardSyncMetaResponse,
    DependencyStatus,
    EmailSuppressionRow,
    HealthDependenciesResponse,
    OutreachContactStateRow,
    OutboundReadinessResponse,
    PaginatedEmailSuppressionsResponse,
    PaginatedOutreachStateResponse,
)
from origenlab_email_pipeline.postgres_dashboard_api.summary import dashboard_summary

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
    "DashboardSummaryResponse",
    "DashboardSyncMetaResponse",
    "DependencyStatus",
    "EmailSuppressionRow",
    "HealthDependenciesResponse",
    "OutreachContactStateRow",
    "OutboundReadinessResponse",
    "PaginatedEmailSuppressionsResponse",
    "PaginatedOutreachStateResponse",
    "assess_postgres_outbound_readiness",
    "classification_actions",
    "classification_recent",
    "classification_summary",
    "dashboard_summary",
    "get_commercial_purchase_event",
    "list_commercial_purchase_events",
    "list_email_suppressions",
    "list_outreach_contact_state",
]
