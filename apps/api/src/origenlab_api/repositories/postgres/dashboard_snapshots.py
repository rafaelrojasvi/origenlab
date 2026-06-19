"""Read ops.pipeline_kv dashboard snapshots from Postgres (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from origenlab_api.repositories.postgres.common import postgres_connection
from origenlab_api.settings import Settings
from origenlab_email_pipeline.postgres_dashboard_api.queries import latest_dashboard_sync
from origenlab_email_pipeline.postgres_dashboard_api.schemas import DashboardSyncMetaResponse

GMAIL_INTERACTION_AUDIT_KV_KEY = "dashboard_gmail_interaction_audit_v1"
OPERATOR_AUTOMATION_STATUS_SNAPSHOT_KV_KEY = "operator_automation_status_snapshot_v1"

DEFAULT_SNAPSHOT_MAX_AGE_SECONDS = 7200


def _iso_timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _dashboard_sync_meta_to_dict(meta: DashboardSyncMetaResponse) -> dict[str, Any]:
    return {
        "table_available": meta.table_available,
        "status": meta.status,
        "latest_sync_id": meta.latest_sync_id,
        "started_at": _iso_timestamp(meta.started_at),
        "finished_at": _iso_timestamp(meta.finished_at),
        "elapsed_seconds": meta.elapsed_seconds,
        "canonical_contact_count": meta.canonical_contact_count,
        "canonical_organization_count": meta.canonical_organization_count,
        "canonical_opportunity_signal_count": meta.canonical_opportunity_signal_count,
        "archive_contact_count": meta.archive_contact_count,
        "archive_organization_count": meta.archive_organization_count,
        "archive_opportunity_signal_count": meta.archive_opportunity_signal_count,
        "email_suppression_count": meta.email_suppression_count,
        "domain_suppression_count": meta.domain_suppression_count,
        "outreach_state_count": meta.outreach_state_count,
        "error_message": meta.error_message,
    }


def get_latest_dashboard_sync_snapshot(settings: Settings) -> dict[str, Any] | None:
    """Latest reporting.dashboard_sync_run row, or None when Postgres unavailable."""
    if not settings.postgres_configured():
        return None
    try:
        with postgres_connection(settings) as conn:
            meta = latest_dashboard_sync(conn)
    except Exception:  # noqa: BLE001
        return None
    if meta.status == "missing_table":
        return None
    return _dashboard_sync_meta_to_dict(meta)


def get_pipeline_kv_snapshot(
    settings: Settings,
    key: str,
) -> dict[str, Any] | None:
    """Return ``{snapshot, updated_at}`` or None when row/table missing."""
    if not settings.postgres_configured():
        return None
    with postgres_connection(settings) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT value_json, updated_at
                    FROM ops.pipeline_kv
                    WHERE kv_key = %s
                    LIMIT 1
                    """,
                    (key,),
                )
            except Exception:  # noqa: BLE001
                return None
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict):
                value_json = row.get("value_json")
                updated_at = row.get("updated_at")
            else:
                value_json, updated_at = row[0], row[1]
            if value_json is None:
                return None
            updated_iso = (
                updated_at.isoformat()
                if hasattr(updated_at, "isoformat")
                else str(updated_at)
            )
            return {
                "snapshot": value_json,
                "updated_at": updated_iso,
            }


def snapshot_age_seconds(updated_at_iso: str, *, now: datetime | None = None) -> int | None:
    try:
        parsed = datetime.fromisoformat(updated_at_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    now_dt = now or datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((now_dt - parsed).total_seconds()))


def snapshot_is_stale(
    updated_at_iso: str,
    *,
    max_age_seconds: int = DEFAULT_SNAPSHOT_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> bool:
    age = snapshot_age_seconds(updated_at_iso, now=now)
    if age is None:
        return True
    return age > max_age_seconds


def get_gmail_interaction_audit_snapshot(settings: Settings) -> dict[str, Any] | None:
    return get_pipeline_kv_snapshot(settings, GMAIL_INTERACTION_AUDIT_KV_KEY)


def get_operator_automation_status_snapshot(settings: Settings) -> dict[str, Any] | None:
    return get_pipeline_kv_snapshot(settings, OPERATOR_AUTOMATION_STATUS_SNAPSHOT_KV_KEY)
