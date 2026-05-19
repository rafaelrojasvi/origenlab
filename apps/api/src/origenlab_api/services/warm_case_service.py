"""Warm case queue service (read-only)."""

from __future__ import annotations

from origenlab_api.repositories.warm_cases import fetch_warm_cases
from origenlab_api.schemas.cases import WarmCasesMeta, WarmCasesResponse
from origenlab_api.settings import Settings


def build_warm_cases_response(
    settings: Settings,
    *,
    days: int = 14,
    limit: int = 50,
    category: str | None = None,
    positive_signal_only: bool = True,
    include_noise: bool = False,
) -> WarmCasesResponse:
    sqlite_path = settings.resolved_sqlite_path()
    items, enrichment_available, reduced_mode, note = fetch_warm_cases(
        sqlite_path,
        days_window=days,
        limit=limit,
        category=category,
        positive_signal_only=positive_signal_only,
        include_noise=include_noise,
    )
    return WarmCasesResponse(
        meta=WarmCasesMeta(
            reduced_mode=reduced_mode,
            count=len(items),
            enrichment_available=enrichment_available,
            note=note,
        ),
        items=items,
    )
