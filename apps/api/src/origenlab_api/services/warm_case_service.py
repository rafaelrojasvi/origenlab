"""Warm case queue service (repository-backed)."""

from __future__ import annotations

from origenlab_api.backends.factory import RepositoryBundle, get_repository_bundle
from origenlab_api.schemas.cases import WarmCasesResponse
from origenlab_api.settings import Settings


def build_warm_cases_response(
    settings: Settings,
    *,
    repos: RepositoryBundle | None = None,
    days: int = 14,
    limit: int = 50,
    category: str | None = None,
    positive_signal_only: bool = True,
    include_noise: bool = False,
) -> WarmCasesResponse:
    bundle = repos or get_repository_bundle(settings)
    items, meta = bundle.warm_cases.list_warm_cases(
        days=days,
        limit=limit,
        category=category,
        positive_signal_only=positive_signal_only,
        include_noise=include_noise,
    )
    return WarmCasesResponse(meta=meta, items=items)
