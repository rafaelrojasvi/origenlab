"""Outbound mirrors (read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from origenlab_api.deps import DbConn, get_settings_dict
from origenlab_api.schemas import (
    OutboundReadinessResponse,
    PaginatedEmailSuppressionsResponse,
    PaginatedOutreachStateResponse,
)
from origenlab_api.services import queries

router = APIRouter(prefix="/outbound", tags=["outbound"])


@router.get("/suppressions/emails", response_model=PaginatedEmailSuppressionsResponse)
def list_email_suppressions(
    conn: DbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Filter by email substring"),
) -> PaginatedEmailSuppressionsResponse:
    return queries.list_email_suppressions(conn, limit=limit, offset=offset, q=q)


@router.get("/contact-state", response_model=PaginatedOutreachStateResponse)
def list_contact_state(
    conn: DbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: str | None = Query(None, description="Exact state (contacted, replied, …)"),
    q: str | None = Query(None, description="Filter by email substring"),
) -> PaginatedOutreachStateResponse:
    return queries.list_outreach_contact_state(
        conn, limit=limit, offset=offset, state=state, q=q
    )


@router.get("/readiness", response_model=OutboundReadinessResponse)
def outbound_readiness(
    conn: DbConn,
    settings: Annotated[dict[str, str | bool], Depends(get_settings_dict)],
    max_staleness_days: float = Query(30.0, ge=1.0, le=365.0),
) -> OutboundReadinessResponse:
    return queries.assess_postgres_outbound_readiness(
        conn,
        postgres_url_redacted=str(settings.get("postgres_url_redacted", "")),
        gmail_user=str(settings.get("gmail_user", "")),
        max_staleness_days=max_staleness_days,
    )
