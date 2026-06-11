"""Operator automation status service (Postgres snapshot with filesystem fallback)."""

from __future__ import annotations

from origenlab_api.repositories.automation_status_fs import get_automation_status_from_active_current
from origenlab_api.repositories.postgres import dashboard_snapshots as snapshot_repo
from origenlab_api.schemas.operator_automation import OperatorAutomationStatusResponse
from origenlab_api.settings import Settings


def build_operator_automation_status_response(
    settings: Settings,
    *,
    mirror_cooldown_seconds: int = 900,
    snapshot_max_age_seconds: int = snapshot_repo.DEFAULT_SNAPSHOT_MAX_AGE_SECONDS,
) -> OperatorAutomationStatusResponse:
    pg_row = snapshot_repo.get_operator_automation_status_snapshot(settings)
    if pg_row is not None:
        snapshot = pg_row["snapshot"]
        updated_at = pg_row["updated_at"]
        stale = snapshot_repo.snapshot_is_stale(
            updated_at,
            max_age_seconds=snapshot_max_age_seconds,
        )
        enriched = {
            **snapshot,
            "source": "postgres_snapshot",
            "snapshot_updated_at": updated_at,
            "snapshot_stale": stale,
        }
        return OperatorAutomationStatusResponse.model_validate(enriched)

    data = get_automation_status_from_active_current(
        settings,
        mirror_cooldown_seconds=mirror_cooldown_seconds,
    )
    data["source"] = "filesystem_active_current"
    data["snapshot_updated_at"] = None
    data["snapshot_stale"] = None
    return OperatorAutomationStatusResponse.model_validate(data)
