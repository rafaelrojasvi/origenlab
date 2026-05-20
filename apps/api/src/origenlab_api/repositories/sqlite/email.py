"""SQLite recent emails repository (review queue)."""

from __future__ import annotations

from origenlab_api.repositories.email import list_recent_emails
from origenlab_api.repositories.email_types import RecentEmailsQueryResult
from origenlab_api.schemas.common import ResponseMeta
from origenlab_api.settings import Settings


class SqliteEmailRecentRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_recent(
        self,
        *,
        days: int = 7,
        limit: int = 50,
        exclude_noise: bool = True,
        folder: str | None = None,
    ) -> RecentEmailsQueryResult:
        sqlite_path = self._settings.resolved_sqlite_path()
        rows, enrichment_available, reduced_mode, scope_note = list_recent_emails(
            sqlite_path,
            days_window=days,
            limit=limit,
            exclude_noise=exclude_noise,
            folder=folder,
        )
        return RecentEmailsQueryResult(
            items=rows,
            meta=ResponseMeta.for_sqlite(sqlite_path if sqlite_path.is_file() else None),
            enrichment_available=enrichment_available,
            reduced_mode=reduced_mode,
            scope_note=scope_note,
        )
