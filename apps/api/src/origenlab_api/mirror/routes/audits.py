"""Mirror audit snapshot routes (read-only Postgres evidence)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from origenlab_api.repositories.postgres import dashboard_snapshots as snapshot_repo
from origenlab_api.schemas.dashboard_snapshots import (
    GmailInteractionAuditDomainRow,
    GmailInteractionAuditResponse,
    GmailInteractionAuditSnapshot,
)
from origenlab_api.settings import Settings, get_settings

router = APIRouter(tags=["postgres-mirror"])


@router.get("/gmail-interactions", response_model=GmailInteractionAuditResponse)
def mirror_gmail_interaction_audit(
    settings: Settings = Depends(get_settings),
) -> GmailInteractionAuditResponse:
    """Compact Gmail/SQLite interaction audit published by operator mirror sync."""
    row = snapshot_repo.get_gmail_interaction_audit_snapshot(settings)
    if row is None:
        return GmailInteractionAuditResponse(
            status="snapshot_missing",
            message="snapshot_missing",
            snapshot=None,
            updated_at=None,
            source=None,
            snapshot_stale=None,
        )

    raw = row["snapshot"]
    domains = [
        GmailInteractionAuditDomainRow.model_validate(item)
        for item in (raw.get("domains") or [])
    ]
    snapshot = GmailInteractionAuditSnapshot(
        schema_version=int(raw.get("schema_version") or 1),
        generated_at_utc=str(raw.get("generated_at_utc") or ""),
        source=str(raw.get("source") or ""),
        lookback_days=int(raw.get("lookback_days") or 0),
        domains=domains,
    )
    updated_at = row["updated_at"]
    stale = snapshot_repo.snapshot_is_stale(updated_at)
    return GmailInteractionAuditResponse(
        status="ok",
        message="ok",
        snapshot=snapshot,
        updated_at=updated_at,
        source="postgres_snapshot",
        snapshot_stale=stale,
    )
