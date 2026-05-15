"""Dashboard summary."""

from __future__ import annotations

from fastapi import APIRouter

from origenlab_api.deps import DbConn
from origenlab_api.schemas import DashboardSummaryResponse
from origenlab_api.services import queries

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(conn: DbConn) -> DashboardSummaryResponse:
    return queries.dashboard_summary(conn)
