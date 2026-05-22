"""Read-only metadata (sync watermarks, etc.)."""

from __future__ import annotations

from fastapi import APIRouter

from origenlab_api.deps import DbConn
from origenlab_api.schemas import DashboardSyncMetaResponse
from origenlab_email_pipeline.postgres_dashboard_api.queries import latest_dashboard_sync

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/dashboard-sync", response_model=DashboardSyncMetaResponse)
def dashboard_sync_meta(conn: DbConn) -> DashboardSyncMetaResponse:
    """Latest row from reporting.dashboard_sync_run (mirror sync audit)."""
    return latest_dashboard_sync(conn)
