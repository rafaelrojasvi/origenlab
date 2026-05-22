"""Mirror outbound routes (read-only Postgres reports)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from origenlab_api.mirror.deps import (
    MirrorDbConn,
    mirror_gmail_user,
    mirror_postgres_url_redacted,
)
from origenlab_api.settings import Settings, get_settings
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import (
    list_email_suppressions,
    list_outreach_contact_state,
)
from origenlab_email_pipeline.postgres_dashboard_api.outbound_readiness import (
    assess_postgres_outbound_readiness,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    OutboundReadinessResponse,
    PaginatedEmailSuppressionsResponse,
    PaginatedOutreachStateResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("/suppressions/emails", response_model=PaginatedEmailSuppressionsResponse)
def mirror_email_suppressions(
    conn: MirrorDbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Filter by email substring"),
) -> PaginatedEmailSuppressionsResponse:
    return list_email_suppressions(conn, limit=limit, offset=offset, q=q)


@router.get("/contact-state", response_model=PaginatedOutreachStateResponse)
def mirror_outreach_contact_state(
    conn: MirrorDbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: str | None = Query(None, description="Exact state (contacted, replied, …)"),
    q: str | None = Query(None, description="Filter by email substring"),
) -> PaginatedOutreachStateResponse:
    return list_outreach_contact_state(
        conn, limit=limit, offset=offset, state=state, q=q
    )


@router.get("/readiness", response_model=OutboundReadinessResponse)
def mirror_outbound_readiness(
    conn: MirrorDbConn,
    settings: Settings = Depends(get_settings),
    max_staleness_days: float = Query(30.0, ge=1.0, le=365.0),
) -> OutboundReadinessResponse:
    """Read-only Postgres mirror readiness report (not permission to send)."""
    return assess_postgres_outbound_readiness(
        conn,
        postgres_url_redacted=mirror_postgres_url_redacted(settings),
        gmail_user=mirror_gmail_user(),
        max_staleness_days=max_staleness_days,
    )
