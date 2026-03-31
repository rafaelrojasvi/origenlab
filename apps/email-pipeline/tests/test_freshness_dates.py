"""Plausible-date policy for mart timeline (not raw archive)."""

from __future__ import annotations

from datetime import date, timedelta

from origenlab_email_pipeline.freshness_dates import (
    MART_DATE_SLACK_DAYS_DEFAULT,
    email_date_iso_for_mart_timeline,
)


def test_plausible_iso_accepted_before_limit() -> None:
    ref = date(2026, 3, 30)
    s = email_date_iso_for_mart_timeline(
        "2026-03-28T09:29:22-07:00",
        slack_days=2,
        today=ref,
    )
    assert s == "2026-03-28T09:29:22-07:00"


def test_future_outlier_excluded_from_timeline() -> None:
    ref = date(2026, 3, 30)
    assert (
        email_date_iso_for_mart_timeline(
            "2033-06-09T15:09:53+01:00",
            slack_days=2,
            today=ref,
        )
        is None
    )


def test_boundary_inclusive_within_slack() -> None:
    ref = date(2026, 3, 30)
    limit_day = ref + timedelta(days=2)
    iso = f"{limit_day.isoformat()}T12:00:00+00:00"
    assert email_date_iso_for_mart_timeline(iso, slack_days=2, today=ref) == iso


def test_unparseable_string_still_passes_through() -> None:
    ref = date(2026, 3, 30)
    weird = "not-a-date-but-kept"
    assert email_date_iso_for_mart_timeline(weird, slack_days=2, today=ref) == weird


def test_empty_returns_none() -> None:
    assert email_date_iso_for_mart_timeline(None) is None
    assert email_date_iso_for_mart_timeline("  ") is None


def test_default_slack_constant_sane() -> None:
    assert 0 <= MART_DATE_SLACK_DAYS_DEFAULT <= 30
