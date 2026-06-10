"""Operator automation status service (filesystem read-only)."""

from __future__ import annotations

from origenlab_api.repositories.automation_status_fs import get_automation_status_from_active_current
from origenlab_api.schemas.operator_automation import OperatorAutomationStatusResponse
from origenlab_api.settings import Settings


def build_operator_automation_status_response(
    settings: Settings,
    *,
    mirror_cooldown_seconds: int = 900,
) -> OperatorAutomationStatusResponse:
    data = get_automation_status_from_active_current(
        settings,
        mirror_cooldown_seconds=mirror_cooldown_seconds,
    )
    return OperatorAutomationStatusResponse.model_validate(data)
