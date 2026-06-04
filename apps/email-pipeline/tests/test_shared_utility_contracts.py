"""Characterization contracts for small shared root utilities (no production DB, no network)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta

import pytest

from origenlab_email_pipeline.contact_export_queries import (
    CONTACT_MASTER_CANDIDATE_AUDIT_COLUMN_NAMES,
    CONTACT_MASTER_MARKETING_EXPORT_COLUMN_NAMES,
    sql_contact_master_candidate_audit_contacts,
    sql_contact_master_marketing_export_candidates,
)
from origenlab_email_pipeline.freshness_dates import email_date_iso_for_mart_timeline
from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables
from origenlab_email_pipeline import pipeline_run_recorder as recorder
from origenlab_email_pipeline.timeutil import now_iso

_REF_DAY = date(2026, 6, 4)
_NOW_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# --- A. timeutil -----------------------------------------------------------------


def test_now_iso_format_contract() -> None:
    s = now_iso()
    assert _NOW_ISO_PATTERN.fullmatch(s) is not None
    assert s.endswith("Z")
    assert "." not in s


# --- B. freshness_dates ----------------------------------------------------------


def test_freshness_none_and_blank_return_none() -> None:
    assert email_date_iso_for_mart_timeline(None, today=_REF_DAY) is None
    assert email_date_iso_for_mart_timeline("", today=_REF_DAY) is None
    assert email_date_iso_for_mart_timeline("  \t  ", today=_REF_DAY) is None


def test_freshness_past_and_current_dates_pass_through() -> None:
    past = "2026-01-15T10:00:00Z"
    current = "2026-06-04T08:00:00+00:00"
    assert email_date_iso_for_mart_timeline(past, today=_REF_DAY) == past
    assert email_date_iso_for_mart_timeline(current, today=_REF_DAY) == current


def test_freshness_default_slack_allows_plus_two_days() -> None:
    within = f"{(_REF_DAY + timedelta(days=2)).isoformat()}T12:00:00Z"
    assert email_date_iso_for_mart_timeline(within, today=_REF_DAY) == within


def test_freshness_default_slack_filters_plus_three_days() -> None:
    beyond = f"{(_REF_DAY + timedelta(days=3)).isoformat()}T12:00:00Z"
    assert email_date_iso_for_mart_timeline(beyond, today=_REF_DAY) is None


def test_freshness_unparseable_non_empty_passes_through() -> None:
    weird = "not-a-parseable-date"
    assert email_date_iso_for_mart_timeline(weird, today=_REF_DAY) == weird


def test_freshness_negative_slack_clamped_to_zero() -> None:
    tomorrow = f"{(_REF_DAY + timedelta(days=1)).isoformat()}T00:00:00Z"
    assert email_date_iso_for_mart_timeline(tomorrow, slack_days=-5, today=_REF_DAY) is None
    today_iso = f"{_REF_DAY.isoformat()}T00:00:00Z"
    assert email_date_iso_for_mart_timeline(today_iso, slack_days=-1, today=_REF_DAY) == today_iso


def test_freshness_huge_slack_resets_to_default() -> None:
    beyond_default = f"{(_REF_DAY + timedelta(days=3)).isoformat()}T00:00:00Z"
    assert email_date_iso_for_mart_timeline(beyond_default, slack_days=9999, today=_REF_DAY) is None
    within_default = f"{(_REF_DAY + timedelta(days=2)).isoformat()}T00:00:00Z"
    assert email_date_iso_for_mart_timeline(within_default, slack_days=9999, today=_REF_DAY) == within_default


# --- C. contact_export_queries ---------------------------------------------------


def test_marketing_export_sql_shape_contract() -> None:
    sql = sql_contact_master_marketing_export_candidates()
    assert "FROM contact_master" in sql
    assert "LIMIT ?" in sql
    assert "lower(trim(email)) AS contact_email" in sql
    assert CONTACT_MASTER_MARKETING_EXPORT_COLUMN_NAMES == (
        "contact_email",
        "recipient_name",
        "institution_name",
        "total_emails",
        "last_seen_at",
        "confidence_score",
    )


def test_candidate_audit_sql_shape_contract() -> None:
    sql = sql_contact_master_candidate_audit_contacts()
    assert "FROM contact_master" in sql
    assert "LIMIT ?" in sql
    assert "NULL AS id_lead" in sql
    assert CONTACT_MASTER_CANDIDATE_AUDIT_COLUMN_NAMES == (
        "contact_email",
        "institution_name",
        "fit_bucket",
        "id_lead",
    )


# --- D. pipeline_meta_schema -----------------------------------------------------


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def test_ensure_pipeline_meta_tables_idempotent_and_columns() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        ensure_pipeline_meta_tables(conn)
        ensure_pipeline_meta_tables(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        }
        assert "pipeline_run" in tables
        assert "pipeline_kv" in tables
        assert _table_columns(conn, "pipeline_run") == [
            "id",
            "started_at",
            "finished_at",
            "script_name",
            "argv_json",
            "git_describe",
            "notes",
        ]
        assert _table_columns(conn, "pipeline_kv") == ["k", "v", "updated_at"]
    finally:
        conn.close()


# --- E. pipeline_run_recorder ----------------------------------------------------


@pytest.fixture
def recorder_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def deterministic_recorder(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    stamps = [
        "2026-06-04T10:00:00Z",
        "2026-06-04T10:00:01Z",
        "2026-06-04T10:00:02Z",
        "2026-06-04T10:00:03Z",
    ]
    idx = {"i": 0}

    def _next_iso() -> str:
        i = idx["i"]
        idx["i"] = min(i + 1, len(stamps) - 1)
        return stamps[i]

    monkeypatch.setattr(recorder, "now_iso", _next_iso)
    monkeypatch.setattr(recorder, "get_git_describe", lambda fallback="": "test-sha")
    monkeypatch.setattr(recorder, "argv_json_default", lambda: json.dumps(["test"]))
    return stamps


def test_start_run_inserts_expected_row(
    recorder_conn: sqlite3.Connection,
    deterministic_recorder: list[str],
) -> None:
    run_id = recorder.start_run(
        recorder_conn,
        script_name="scripts/qa/example.py",
        notes="unit-test",
    )
    assert isinstance(run_id, int)
    assert run_id >= 1
    row = recorder_conn.execute(
        "SELECT started_at, finished_at, script_name, argv_json, git_describe, notes FROM pipeline_run WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == deterministic_recorder[0]
    assert row[1] is None
    assert row[2] == "scripts/qa/example.py"
    assert row[3] == '["test"]'
    assert row[4] == "test-sha"
    assert row[5] == "unit-test"


def test_finish_run_sets_finished_at(
    recorder_conn: sqlite3.Connection,
    deterministic_recorder: list[str],
) -> None:
    run_id = recorder.start_run(recorder_conn, script_name="finish_me.py")
    recorder.finish_run(recorder_conn, run_id)
    finished = recorder_conn.execute(
        "SELECT finished_at FROM pipeline_run WHERE id = ?", (run_id,)
    ).fetchone()[0]
    assert finished == deterministic_recorder[1]


def test_set_kv_insert_then_update(
    recorder_conn: sqlite3.Connection,
    deterministic_recorder: list[str],
) -> None:
    recorder.set_kv(recorder_conn, "mart.build", "v1")
    recorder.set_kv(recorder_conn, "mart.build", "v2")
    row = recorder_conn.execute(
        "SELECT v, updated_at FROM pipeline_kv WHERE k = ?", ("mart.build",)
    ).fetchone()
    assert row[0] == "v2"
    assert row[1] == deterministic_recorder[1]


def test_get_kv_hit_and_miss(recorder_conn: sqlite3.Connection) -> None:
    recorder.set_kv(recorder_conn, "exists", "yes")
    assert recorder.get_kv(recorder_conn, "exists") == "yes"
    assert recorder.get_kv(recorder_conn, "missing") is None
