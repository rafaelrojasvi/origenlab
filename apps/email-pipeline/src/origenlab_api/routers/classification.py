"""Read-only canonical Gmail classification mirror endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from origenlab_api.deps import DbConn
from origenlab_api.schemas import (
    ClassificationActionsResponse,
    ClassificationRecentResponse,
    ClassificationSummaryResponse,
)
from origenlab_email_pipeline.postgres_dashboard_api.classification import (
    classification_actions as fetch_classification_actions,
    classification_recent as fetch_classification_recent,
    classification_summary as fetch_classification_summary,
)

router = APIRouter(prefix="/classification", tags=["classification"])


@router.get("/summary", response_model=ClassificationSummaryResponse)
def get_classification_summary(conn: DbConn) -> ClassificationSummaryResponse:
    """KPI counts from reporting.email_classification_canonical (canonical scope only)."""
    return fetch_classification_summary(conn)


@router.get("/recent", response_model=ClassificationRecentResponse)
def get_classification_recent(
    conn: DbConn,
    label: Annotated[str | None, Query(description="Filter by predicted_label")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ClassificationRecentResponse:
    """Recent classified emails (heuristic QA, not CRM truth)."""
    return fetch_classification_recent(conn, label=label, limit=limit)


@router.get("/actions", response_model=ClassificationActionsResponse)
def get_classification_actions(conn: DbConn) -> ClassificationActionsResponse:
    """Suggested triage actions grouped by recommended_action."""
    return fetch_classification_actions(conn)
