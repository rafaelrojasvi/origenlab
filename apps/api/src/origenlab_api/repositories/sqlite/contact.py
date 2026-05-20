"""SQLite contact intelligence repository."""

from __future__ import annotations

from origenlab_api.repositories.contact import fetch_contact_intelligence
from origenlab_api.repositories.contact_types import ContactQueryResult
from origenlab_api.settings import Settings


class SqliteContactRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_contact_detail(self, email_raw: str) -> ContactQueryResult:
        contact, outreach, sent, warnings, reduced_mode = fetch_contact_intelligence(
            self._settings.resolved_sqlite_path(),
            self._settings.resolved_active_current(),
            email_raw,
        )
        return ContactQueryResult(
            contact=contact,
            outreach=outreach,
            sent_history=sent,
            warnings=warnings,
            reduced_mode=reduced_mode,
            data_source="sqlite",
        )
