"""Shared types for recent-email repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from origenlab_api.schemas.common import ResponseMeta


@dataclass(frozen=True)
class RecentEmailsQueryResult:
    items: list[dict[str, Any]]
    meta: ResponseMeta
    enrichment_available: bool
    reduced_mode: bool
    scope_note: str
