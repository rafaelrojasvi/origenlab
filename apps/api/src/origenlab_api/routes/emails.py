"""Recent canonical emails (read-only previews)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from origenlab_api.schemas.emails import EmailsRecentResponse
from origenlab_api.services.email_service import build_emails_recent_response
from origenlab_api.settings import Settings, get_settings

router = APIRouter(tags=["emails"])


@router.get("/emails/recent", response_model=EmailsRecentResponse)
def emails_recent(
    settings: Settings = Depends(get_settings),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    exclude_noise: bool = Query(True),
    folder: str | None = Query(None, description="Optional filter on source_file / folder substring"),
) -> EmailsRecentResponse:
    return build_emails_recent_response(
        settings,
        days=days,
        limit=limit,
        exclude_noise=exclude_noise,
        folder=folder,
    )
