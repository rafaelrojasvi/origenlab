"""SQLite / active-current CSV equipment opportunities repository."""

from __future__ import annotations

from typing import Any

from origenlab_api.repositories.equipment_opportunities import fetch_equipment_opportunities
from origenlab_api.schemas.opportunities import EquipmentOpportunitiesMeta
from origenlab_api.settings import Settings


class SqliteEquipmentOpportunityRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_equipment(
        self,
        *,
        limit: int = 50,
        priority: int | None = None,
        next_action: str | None = None,
        safe_channel: str | None = None,
        include_account_intelligence: bool = True,
    ) -> tuple[list[dict[str, Any]], EquipmentOpportunitiesMeta]:
        return fetch_equipment_opportunities(
            self._settings.resolved_active_current(),
            limit=limit,
            priority=priority,
            next_action=next_action,
            safe_channel=safe_channel,
            include_account_intelligence=include_account_intelligence,
        )
