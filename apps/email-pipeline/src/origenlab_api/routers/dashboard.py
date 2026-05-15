"""Dashboard summary."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from origenlab_api.deps import DbConn
from origenlab_api.schemas import DashboardSummaryResponse
from origenlab_api.services import queries

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    conn: DbConn,
    scope: Literal["canonical", "archive"] = Query(
        "canonical",
        description="canonical = Gmail operativo mirror; archive = full mart (explicit).",
    ),
) -> DashboardSummaryResponse:
    return queries.dashboard_summary(conn, scope=scope)
