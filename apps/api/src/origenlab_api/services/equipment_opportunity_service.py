"""Equipment-first operator queue service (repository-backed)."""

from __future__ import annotations

from origenlab_api.backends.factory import RepositoryBundle, get_repository_bundle
from origenlab_api.path_redaction import enrich_equipment_meta_paths
from origenlab_api.schemas.opportunities import (
    EquipmentOpportunitiesMeta,
    EquipmentOpportunitiesResponse,
    EquipmentOpportunityItem,
)
from origenlab_api.settings import Settings


def build_equipment_opportunities_response(
    settings: Settings,
    *,
    repos: RepositoryBundle | None = None,
    limit: int = 50,
    priority: int | None = None,
    next_action: str | None = None,
    safe_channel: str | None = None,
    include_account_intelligence: bool = True,
) -> EquipmentOpportunitiesResponse:
    bundle = repos or get_repository_bundle(settings)
    rows, meta = bundle.equipment.list_equipment(
        limit=limit,
        priority=priority,
        next_action=next_action,
        safe_channel=safe_channel,
        include_account_intelligence=include_account_intelligence,
    )
    return EquipmentOpportunitiesResponse(
        meta=EquipmentOpportunitiesMeta.model_validate(enrich_equipment_meta_paths(meta.model_dump())),
        items=[EquipmentOpportunityItem.model_validate(r) for r in rows],
    )
