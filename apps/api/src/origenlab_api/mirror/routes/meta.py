"""Mirror metadata routes (sync watermarks)."""

from __future__ import annotations

from fastapi import APIRouter

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.queries import latest_dashboard_sync
from origenlab_email_pipeline.postgres_dashboard_api.schemas import DashboardSyncMetaResponse

router = APIRouter(tags=["postgres-mirror"])


@router.get("/dashboard-sync", response_model=DashboardSyncMetaResponse)
def mirror_dashboard_sync_meta(conn: MirrorDbConn) -> DashboardSyncMetaResponse:
    """Latest row from reporting.dashboard_sync_run (mirror sync audit)."""
    return latest_dashboard_sync(conn)
