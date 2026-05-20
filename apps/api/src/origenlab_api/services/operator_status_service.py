"""Operator status service (repository-backed)."""

from __future__ import annotations

from origenlab_api.backends.factory import RepositoryBundle, get_repository_bundle
from origenlab_api.schemas.operator import OperatorStatusResponse
from origenlab_api.settings import Settings


def build_operator_status_response(
    settings: Settings,
    *,
    repos: RepositoryBundle | None = None,
    max_staleness_days: float = 14.0,
) -> OperatorStatusResponse:
    bundle = repos or get_repository_bundle(settings)
    data = bundle.operator.get_status(max_staleness_days=max_staleness_days)
    return OperatorStatusResponse.model_validate(data)
