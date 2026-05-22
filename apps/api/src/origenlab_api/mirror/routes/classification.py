"""Mirror classification routes (read-only Postgres QA heuristics)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.classification import (
    classification_actions,
    classification_recent,
    classification_summary,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    ClassificationActionsResponse,
    ClassificationRecentResponse,
    ClassificationSummaryResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("/summary", response_model=ClassificationSummaryResponse)
def mirror_classification_summary(conn: MirrorDbConn) -> ClassificationSummaryResponse:
    return classification_summary(conn)


@router.get("/recent", response_model=ClassificationRecentResponse)
def mirror_classification_recent(
    conn: MirrorDbConn,
    label: Annotated[str | None, Query(description="Filter by predicted_label")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ClassificationRecentResponse:
    return classification_recent(conn, label=label, limit=limit)


@router.get("/actions", response_model=ClassificationActionsResponse)
def mirror_classification_actions(conn: MirrorDbConn) -> ClassificationActionsResponse:
    return classification_actions(conn)
