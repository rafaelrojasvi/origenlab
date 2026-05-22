"""Postgres read queries for dashboard mirror metadata (API-3 shared)."""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_one, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    POSTGRES_MIRROR_NOTE,
    DashboardSyncMetaResponse,
)


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_seconds(
    started_at: datetime | str | None,
    finished_at: datetime | str | None,
) -> float | None:
    started = _parse_dt(started_at)
    finished = _parse_dt(finished_at)
    if started is None or finished is None:
        return None
    return round((finished - started).total_seconds(), 3)


def latest_dashboard_sync(conn: Connection) -> DashboardSyncMetaResponse:
    """Return the most recent reporting.dashboard_sync_run row, if any."""
    if not table_exists(conn, schema="reporting", table="dashboard_sync_run"):
        return DashboardSyncMetaResponse(table_available=False, status="missing_table")

    row = fetch_one(
        conn,
        """
        SELECT
          id,
          started_at,
          finished_at,
          status,
          canonical_contact_count,
          canonical_organization_count,
          canonical_opportunity_signal_count,
          archive_contact_count,
          archive_organization_count,
          archive_opportunity_signal_count,
          email_suppression_count,
          domain_suppression_count,
          outreach_state_count,
          error_message
        FROM reporting.dashboard_sync_run
        ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
        LIMIT 1
        """,
    )
    if not row:
        return DashboardSyncMetaResponse(table_available=True, status="no_rows")

    raw_status = str(row.get("status") or "unknown").strip().lower()
    if raw_status in ("success", "failed", "dry_run"):
        mapped_status = raw_status
    else:
        mapped_status = "unknown"

    started_at = row.get("started_at")
    finished_at = row.get("finished_at")
    return DashboardSyncMetaResponse(
        table_available=True,
        status=mapped_status,  # type: ignore[arg-type]
        latest_sync_id=int(row["id"]) if row.get("id") is not None else None,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=_elapsed_seconds(started_at, finished_at),
        postgres_mirror_note=POSTGRES_MIRROR_NOTE,
        canonical_contact_count=int(row.get("canonical_contact_count") or 0),
        canonical_organization_count=int(row.get("canonical_organization_count") or 0),
        canonical_opportunity_signal_count=int(
            row.get("canonical_opportunity_signal_count") or 0
        ),
        archive_contact_count=int(row.get("archive_contact_count") or 0),
        archive_organization_count=int(row.get("archive_organization_count") or 0),
        archive_opportunity_signal_count=int(
            row.get("archive_opportunity_signal_count") or 0
        ),
        email_suppression_count=int(row.get("email_suppression_count") or 0),
        domain_suppression_count=int(row.get("domain_suppression_count") or 0),
        outreach_state_count=int(row.get("outreach_state_count") or 0),
        error_message=row.get("error_message"),
    )
