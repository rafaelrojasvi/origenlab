"""Recent emails service (read-only)."""

from __future__ import annotations

from origenlab_api.repositories.email import list_recent_emails
from origenlab_api.schemas.common import ResponseMeta
from origenlab_api.schemas.emails import EmailRecentRow, EmailsRecentResponse
from origenlab_api.settings import Settings


def build_emails_recent_response(
    settings: Settings,
    *,
    days: int = 7,
    limit: int = 50,
    exclude_noise: bool = True,
    folder: str | None = None,
) -> EmailsRecentResponse:
    sqlite_path = settings.resolved_sqlite_path()
    rows, enrichment_available, reduced_mode, scope_note = list_recent_emails(
        sqlite_path,
        days_window=days,
        limit=limit,
        exclude_noise=exclude_noise,
        folder=folder,
    )
    items = [EmailRecentRow.model_validate(r) for r in rows]
    return EmailsRecentResponse(
        meta=ResponseMeta.for_sqlite(sqlite_path if sqlite_path.is_file() else None),
        items=items,
        total_returned=len(items),
        days_window=days,
        scope_note=scope_note,
        enrichment_available=enrichment_available,
        reduced_mode=reduced_mode,
    )
