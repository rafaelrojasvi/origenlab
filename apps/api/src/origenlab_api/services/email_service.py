"""Recent emails service (repository-backed)."""

from __future__ import annotations

from origenlab_api.backends.factory import RepositoryBundle, get_repository_bundle
from origenlab_api.schemas.emails import EmailRecentRow, EmailsRecentResponse
from origenlab_api.settings import Settings


def build_emails_recent_response(
    settings: Settings,
    *,
    repos: RepositoryBundle | None = None,
    days: int = 7,
    limit: int = 50,
    exclude_noise: bool = True,
    folder: str | None = None,
) -> EmailsRecentResponse:
    bundle = repos or get_repository_bundle(settings)
    result = bundle.email_recent.list_recent(
        days=days,
        limit=limit,
        exclude_noise=exclude_noise,
        folder=folder,
    )
    items = [EmailRecentRow.model_validate(r) for r in result.items]
    return EmailsRecentResponse(
        meta=result.meta,
        items=items,
        total_returned=len(items),
        days_window=days,
        scope_note=result.scope_note,
        enrichment_available=result.enrichment_available,
        reduced_mode=result.reduced_mode,
    )
