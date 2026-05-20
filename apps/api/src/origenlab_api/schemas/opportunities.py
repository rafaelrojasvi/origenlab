"""Equipment-first operator opportunities (read-only CSV)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EquipmentOpportunitiesMeta(BaseModel):
    data_source: Literal["active_current_csv", "postgres_mirror"] = "active_current_csv"
    read_only: bool = True
    count: int = 0
    source_path: str = ""
    campaign_mode: str | None = None
    reduced_mode: bool = False
    note: str = ""


class EquipmentOpportunityItem(BaseModel):
    priority_rank: int
    codigo_licitacion: str = ""
    buyer: str = ""
    region: str = ""
    close_date: str = ""
    equipment_category: str = ""
    item_description: str = ""
    next_action: str = ""
    safe_channel: str = ""
    supplier_needed: str = ""
    contact_status: str = ""
    operator_note: str = ""


class EquipmentOpportunitiesResponse(BaseModel):
    meta: EquipmentOpportunitiesMeta
    items: list[EquipmentOpportunityItem] = Field(default_factory=list)
