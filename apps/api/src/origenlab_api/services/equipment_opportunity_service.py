"""Equipment-first operator queue service (read-only CSV)."""

from __future__ import annotations

from origenlab_api.repositories.equipment_opportunities import fetch_equipment_opportunities
from origenlab_api.schemas.opportunities import EquipmentOpportunitiesResponse, EquipmentOpportunityItem
from origenlab_api.settings import Settings


def build_equipment_opportunities_response(
    settings: Settings,
    *,
    limit: int = 50,
    priority: int | None = None,
    next_action: str | None = None,
    safe_channel: str | None = None,
    include_account_intelligence: bool = True,
) -> EquipmentOpportunitiesResponse:
    active_current = settings.resolved_active_current()
    rows, meta = fetch_equipment_opportunities(
        active_current,
        limit=limit,
        priority=priority,
        next_action=next_action,
        safe_channel=safe_channel,
        include_account_intelligence=include_account_intelligence,
    )
    return EquipmentOpportunitiesResponse(
        meta=meta,
        items=[EquipmentOpportunityItem.model_validate(r) for r in rows],
    )
