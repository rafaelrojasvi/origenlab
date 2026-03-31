"""Plausible-date policy for **derived** mart and freshness (raw archive unchanged).

Raw ``emails.date_iso`` stays as ingested. When building ``contact_master`` /
``organization_master`` (and related derived ``sent_at``), timestamps that are
clearly **too far in the future** (bad headers, spam) are **excluded from
min/max timeline fields only** — message counts and other logic still use the row.

Rule (aligned with **Salud de datos** / ``load_email_date_health``):

- Parse the calendar date from ``date_iso`` when possible (ISO-8601 subset + ``Z``).
- If parsing fails, treat as **eligible** for timeline bounds (same as SQLite
  ``date(date_iso) IS NULL`` branch in plausible-max queries — conservative).
- If parsed date is **strictly after** ``today + slack_days``, **omit** this
  value from timeline aggregation (return ``None`` from
  ``email_date_iso_for_mart_timeline``).
- ``slack_days`` default **2** (clock/skew tolerance).

This module has no Streamlit dependency so tests and mart scripts can import it.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

MART_DATE_SLACK_DAYS_DEFAULT = 2

_ISO_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _try_parse_calendar_date(date_iso: str) -> date | None:
    s = (date_iso or "").strip()
    if not s:
        return None
    u = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(u)
        return dt.date()
    except ValueError:
        pass
    m = _ISO_DATE_PREFIX.match(s)
    if m:
        y, mo, d_ = m.group(1).split("-")
        try:
            return date(int(y), int(mo), int(d_))
        except ValueError:
            return None
    return None


def email_date_iso_for_mart_timeline(
    date_iso: str | None,
    *,
    slack_days: int = MART_DATE_SLACK_DAYS_DEFAULT,
    today: date | None = None,
) -> str | None:
    """Return ``date_iso`` if it may contribute to mart first/last_seen (or document sent_at).

    Returns ``None`` if empty/whitespace, or if the parsed calendar date is
    strictly after ``today + slack_days`` (outlier — do not use for bounds).
    """
    if date_iso is None:
        return None
    s = str(date_iso).strip()
    if not s:
        return None
    n = slack_days
    if n < 0:
        n = 0
    if n > 3660:
        n = MART_DATE_SLACK_DAYS_DEFAULT
    tday = today or date.today()
    limit = tday + timedelta(days=n)
    parsed = _try_parse_calendar_date(s)
    if parsed is None:
        return s
    if parsed > limit:
        return None
    return s
