"""Mirror dashboard summary (Postgres mart/outbound counts)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.schemas import DashboardSummaryResponse
from origenlab_email_pipeline.postgres_dashboard_api.summary import dashboard_summary

router = APIRouter(tags=["postgres-mirror"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def mirror_dashboard_summary(
    conn: MirrorDbConn,
    scope: Literal["canonical", "archive"] = Query(
        "canonical",
        description="canonical = Gmail operativo mirror; archive = full mart (explicit).",
    ),
) -> DashboardSummaryResponse:
    return dashboard_summary(conn, scope=scope)
