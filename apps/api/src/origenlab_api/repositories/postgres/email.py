"""Postgres recent emails (read-only ``api.v_recent_email``)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from origenlab_api.repositories.email import _folder_hint
from origenlab_api.repositories.email_types import RecentEmailsQueryResult
from origenlab_api.repositories.postgres.common import postgres_connection, require_psycopg
from origenlab_api.schemas.common import ResponseMeta
from origenlab_api.settings import Settings

_NOISE_PREDICTED_LABELS = (
    "supplier_noise",
    "admin_noise",
    "noise",
    "marketing_noise",
)

_RECENT_EMAIL_SQL = """
SELECT
  email_id,
  date_iso,
  subject_preview,
  sender_preview,
  source_file,
  folder_hint,
  has_positive_signal,
  has_suppression_signal,
  predicted_label
FROM api.v_recent_email
WHERE (
  length(COALESCE(date_iso, '')) >= 10
  AND left(date_iso, 10) >= %(cutoff_date)s
)
AND (
  %(exclude_noise)s::boolean IS FALSE
  OR (
    COALESCE(has_suppression_signal, FALSE) IS FALSE
    AND (
      predicted_label IS NULL
      OR NOT (lower(trim(predicted_label)) = ANY(%(noise_labels)s))
    )
    AND NOT (
      lower(COALESCE(sender_preview, '')) LIKE '%%mailer-daemon%%'
      OR lower(COALESCE(sender_preview, '')) LIKE '%%mailer daemon%%'
      OR lower(COALESCE(sender_preview, '')) LIKE '%%postmaster%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%undeliverable%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%undelivered%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%delivery status%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%delivery failure%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%failure notice%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%returned mail%%'
      OR lower(COALESCE(subject_preview, '')) LIKE '%%message not delivered%%'
    )
  )
)
AND (
  %(folder)s::text IS NULL
  OR lower(COALESCE(folder_hint, '')) = lower(%(folder)s)
  OR lower(COALESCE(folder_hint, '')) LIKE '%%' || lower(%(folder)s) || '%%'
  OR lower(COALESCE(source_file, '')) LIKE '%%' || lower(%(folder)s) || '%%'
)
ORDER BY date_iso DESC NULLS LAST
LIMIT %(limit)s
"""

_EMPTY_NOTE = (
    "Postgres mirror has no recent emails; run dashboard sync/classification mirror."
)
_NULL_SOURCE_FILE_NOTE = "Postgres mirror does not expose source_file yet."


def date_cutoff_iso(days_window: int) -> str:
    days = max(1, min(int(days_window), 90))
    return (date.today() - timedelta(days=days)).isoformat()


def map_recent_email_row(row: dict[str, Any]) -> dict[str, Any]:
    source_file = _optional_str(row.get("source_file"))
    folder_hint_raw = row.get("folder_hint")
    if source_file:
        folder_hint = _folder_hint(source_file)
    else:
        folder_hint = _optional_str(folder_hint_raw)

    return {
        "email_id": int(row["email_id"]),
        "date_iso": _optional_str(row.get("date_iso")),
        "subject_preview": _str_field(row.get("subject_preview")),
        "sender_preview": _str_field(row.get("sender_preview")),
        "source_file": source_file,
        "folder_hint": folder_hint,
        "has_positive_signal": bool(row.get("has_positive_signal")),
        "has_suppression_signal": bool(row.get("has_suppression_signal")),
    }


def build_scope_note(*, items: list[dict[str, Any]]) -> str:
    if not items:
        return _EMPTY_NOTE
    if any(item.get("source_file") is None for item in items):
        return _NULL_SOURCE_FILE_NOTE
    return ""


class PostgresEmailRecentRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_recent(
        self,
        *,
        days: int = 7,
        limit: int = 50,
        exclude_noise: bool = True,
        folder: str | None = None,
    ) -> RecentEmailsQueryResult:
        require_psycopg()
        cap = max(1, min(int(limit), 200))
        folder_f = (folder or "").strip() or None
        params = {
            "cutoff_date": date_cutoff_iso(days),
            "exclude_noise": exclude_noise,
            "noise_labels": list(_NOISE_PREDICTED_LABELS),
            "folder": folder_f,
            "limit": cap,
        }

        items: list[dict[str, Any]] = []
        pg = require_psycopg()
        with postgres_connection(self._settings) as conn:
            with conn.cursor(row_factory=pg.rows.dict_row) as cur:
                cur.execute(_RECENT_EMAIL_SQL, params)
                for raw in cur.fetchall():
                    items.append(map_recent_email_row(dict(raw)))

        scope_note = build_scope_note(items=items)
        reduced_mode = len(items) == 0
        return RecentEmailsQueryResult(
            items=items,
            meta=ResponseMeta.for_postgres_mirror(),
            enrichment_available=True,
            reduced_mode=reduced_mode,
            scope_note=scope_note,
        )


def _str_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
