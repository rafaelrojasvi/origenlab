"""Postgres warm cases (read-only ``api.v_warm_case``)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from origenlab_api.repositories.postgres.common import postgres_connection, require_psycopg
from origenlab_api.schemas.cases import WarmCaseItem, WarmCasesMeta
from origenlab_api.settings import Settings

# Category filter runs after response-time normalization (mirror stores client_reply, etc.).
_WARM_CASE_SQL = """
SELECT
  case_id,
  last_email_id,
  last_seen_at,
  account_name,
  contact_email,
  subject,
  category,
  status,
  next_action,
  equipment_signal,
  snippet,
  gmail_url
FROM api.v_warm_case
WHERE last_seen_at >= %(cutoff)s
  AND (
    %(include_noise)s::boolean IS TRUE
    OR lower(trim(COALESCE(category, ''))) <> 'bounce'
  )
ORDER BY last_seen_at DESC NULLS LAST
LIMIT %(limit)s
"""

_EMPTY_NOTE = (
    "Postgres mirror has no warm cases; run sync with --include-warm-cases."
)


def utc_cutoff(days_window: int) -> datetime:
    days = max(1, min(int(days_window), 90))
    return datetime.now(timezone.utc) - timedelta(days=days)


def map_warm_case_row(row: dict[str, Any]) -> WarmCaseItem:
    last_email_id = row.get("last_email_id")
    try:
        email_id = int(last_email_id) if last_email_id is not None else 0
    except (TypeError, ValueError):
        email_id = 0

    gmail_url = row.get("gmail_url")
    if gmail_url is not None and not str(gmail_url).strip():
        gmail_url = None

    return WarmCaseItem(
        case_id=_str_field(row.get("case_id")),
        last_email_id=email_id,
        last_seen_at=_format_last_seen(row.get("last_seen_at")),
        account_name=_str_field(row.get("account_name")),
        contact_email=_str_field(row.get("contact_email")),
        subject=_str_field(row.get("subject")),
        category=_str_field(row.get("category")) or "opportunity",  # type: ignore[arg-type]
        status=_str_field(row.get("status")) or "open",  # type: ignore[arg-type]
        next_action=_str_field(row.get("next_action")),
        equipment_signal=_str_field(row.get("equipment_signal")),
        snippet=_str_field(row.get("snippet")),
        gmail_url=gmail_url if isinstance(gmail_url, str) else None,
    )


def build_warm_cases_meta(*, items: list[WarmCaseItem]) -> WarmCasesMeta:
    if items:
        return WarmCasesMeta(
            data_source="postgres_mirror",
            read_only=True,
            reduced_mode=False,
            count=len(items),
            enrichment_available=True,
            note="",
        )
    return WarmCasesMeta(
        data_source="postgres_mirror",
        read_only=True,
        reduced_mode=True,
        count=0,
        enrichment_available=True,
        note=_EMPTY_NOTE,
    )


def _str_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_last_seen(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    text = str(value).strip()
    return text or None


class PostgresWarmCaseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_warm_cases(
        self,
        *,
        days: int = 14,
        limit: int = 50,
        category: str | None = None,
        positive_signal_only: bool = False,
        include_noise: bool = False,
    ) -> tuple[list[WarmCaseItem], WarmCasesMeta]:
        require_psycopg()
        cap = max(1, min(int(limit), 200))
        category_f = (category or "").strip().lower() or None
        fetch_limit = min(cap * 4, 200)

        params = {
            "cutoff": utc_cutoff(days),
            "include_noise": include_noise,
            "limit": fetch_limit,
        }

        from origenlab_api.services.warm_case_output_normalize import normalize_warm_case_items

        raw_items: list[WarmCaseItem] = []
        pg = require_psycopg()
        with postgres_connection(self._settings) as conn:
            with conn.cursor(row_factory=pg.rows.dict_row) as cur:
                cur.execute(_WARM_CASE_SQL, params)
                for raw in cur.fetchall():
                    raw_items.append(map_warm_case_row(dict(raw)))

        items = normalize_warm_case_items(
            raw_items,
            include_noise=include_noise,
            category_filter=category_f,
            positive_signal_only=positive_signal_only,
        )[:cap]
        return items, build_warm_cases_meta(items=items)
