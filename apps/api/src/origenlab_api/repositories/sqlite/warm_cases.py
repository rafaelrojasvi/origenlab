"""SQLite warm cases repository (review queue + heuristics)."""

from __future__ import annotations

from origenlab_api.repositories.warm_cases import fetch_warm_cases
from origenlab_api.schemas.cases import WarmCaseItem, WarmCasesMeta
from origenlab_api.settings import Settings


class SqliteWarmCaseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_warm_cases(
        self,
        *,
        days: int = 14,
        limit: int = 50,
        category: str | None = None,
        positive_signal_only: bool = False,
        include_noise: bool = False,
    ) -> tuple[list[WarmCaseItem], WarmCasesMeta]:
        items, enrichment_available, reduced_mode, note = fetch_warm_cases(
            self._settings.resolved_sqlite_path(),
            days_window=days,
            limit=limit,
            category=category,
            positive_signal_only=positive_signal_only,
            include_noise=include_noise,
        )
        return items, WarmCasesMeta(
            data_source="sqlite",
            read_only=True,
            reduced_mode=reduced_mode,
            count=len(items),
            enrichment_available=enrichment_available,
            note=note,
        )
