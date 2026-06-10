"""Tests for read-only operator automation status command."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from origenlab_email_pipeline.operator_cli.daily_core_manifest import MANIFEST_FILENAME
from origenlab_email_pipeline.operator_cli.dashboard_auto_mirror import STATE_FILENAME as MIRROR_STATE_FILENAME
from origenlab_email_pipeline.operator_cli.mail_auto_refresh import STATE_FILENAME as MAIL_STATE_FILENAME
from origenlab_email_pipeline.operator_cli.operator_automation_status import (
    OperatorAutomationStatusOptions,
    build_operator_automation_status,
    run_operator_automation_status,
)

_T0 = datetime(2026, 6, 10, 18, 30, 0, tzinfo=timezone.utc)
_DAILY_CORE_TS = "2026-06-10T18:12:48+00:00"
_MIRROR_TS = "2026-06-10T18:18:33+00:00"


@pytest.fixture
def active_current(tmp_path: Path) -> Path:
    path = tmp_path / "active" / "current"
    path.mkdir(parents=True)
    return path


def _write_manifest(active_current: Path, **kwargs: object) -> None:
    payload = {
        "schema_version": 1,
        "workflow": "daily-core",
        "generated_at_utc": _DAILY_CORE_TS,
        "status": "success",
        "returncode": 0,
        "steps": [{"label": "gmail-ingest", "returncode": 0}] * 8,
        **kwargs,
    }
    (active_current / MANIFEST_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def _write_mail_state(active_current: Path, **kwargs: object) -> None:
    payload = {
        "dirty": False,
        "last_result": "no_change",
        "last_successful_refresh_at": _DAILY_CORE_TS,
        "last_seen_inbox_total": 403,
        "last_seen_sent_total": 971,
        "consecutive_failures": 0,
        **kwargs,
    }
    (active_current / MAIL_STATE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def _write_mirror_state(active_current: Path, **kwargs: object) -> None:
    payload = {
        "last_result": "success",
        "last_successful_mirror_at": _MIRROR_TS,
        "last_mirrored_daily_core_generated_at": _DAILY_CORE_TS,
        "consecutive_failures": 0,
        **kwargs,
    }
    (active_current / MIRROR_STATE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def _healthy_fixture(active_current: Path) -> Path:
    _write_manifest(active_current)
    _write_mail_state(active_current)
    _write_mirror_state(active_current)
    return active_current.parent.parent


def test_healthy_state(active_current: Path) -> None:
    reports = _healthy_fixture(active_current)
    report = build_operator_automation_status(reports_dir=reports, now=_T0)
    assert report["verdict"] == "healthy"
    assert report["recommended_action"] == "none"
    assert report["mail_auto_refresh"]["dirty"] is False
    assert report["dashboard_auto_mirror"]["mirror_matches_daily_core"] is True


def test_json_output_keys(active_current: Path, capsys: pytest.CaptureFixture[str]) -> None:
    reports = _healthy_fixture(active_current)
    rc = run_operator_automation_status(
        OperatorAutomationStatusOptions(json_output=True),
        reports_dir=reports,
        now=_T0,
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    for key in (
        "generated_at_utc",
        "active_current_dir",
        "verdict",
        "daily_core",
        "mail_auto_refresh",
        "dashboard_auto_mirror",
        "recommended_action",
        "warnings",
    ):
        assert key in data


def test_missing_daily_core_manifest(active_current: Path) -> None:
    _write_mail_state(active_current)
    _write_mirror_state(active_current)
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "create_missing_state_by_running_dry_run"


def test_failed_daily_core_manifest(active_current: Path) -> None:
    _write_manifest(active_current, status="failed", returncode=1)
    _write_mail_state(active_current)
    _write_mirror_state(active_current)
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "blocked"
    assert report["recommended_action"] == "inspect_failed_daily_core"


def test_mail_dirty(active_current: Path) -> None:
    _write_manifest(active_current)
    _write_mail_state(active_current, dirty=True)
    _write_mirror_state(active_current)
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "wait_for_mail_quiet_window"


def test_mail_pending(active_current: Path) -> None:
    _write_manifest(active_current)
    _write_mail_state(active_current, pending_inbox_total=404)
    _write_mirror_state(active_current)
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "attention"
    assert report["mail_auto_refresh"]["pending"] is True


def test_mirror_behind_daily_core(active_current: Path) -> None:
    _write_manifest(active_current)
    _write_mail_state(active_current)
    _write_mirror_state(
        active_current,
        last_mirrored_daily_core_generated_at="2026-06-10T17:00:00+00:00",
        last_successful_mirror_at=(_T0 - timedelta(seconds=1200)).isoformat(),
    )
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "run_auto_mirror_dashboard"
    assert report["dashboard_auto_mirror"]["mirror_matches_daily_core"] is False


def test_mirror_cooldown_when_behind(active_current: Path) -> None:
    _write_manifest(active_current)
    _write_mail_state(active_current)
    _write_mirror_state(
        active_current,
        last_mirrored_daily_core_generated_at="2026-06-10T17:00:00+00:00",
        last_successful_mirror_at=(_T0 - timedelta(seconds=60)).isoformat(),
    )
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
        options=OperatorAutomationStatusOptions(mirror_cooldown_seconds=900),
    )
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "wait_for_mirror_cooldown"
    assert report["dashboard_auto_mirror"]["cooldown_remaining_seconds"] > 0


def test_mirror_cooldown_healthy_when_already_mirrored(active_current: Path) -> None:
    reports = _healthy_fixture(active_current)
    _write_mirror_state(
        active_current,
        last_successful_mirror_at=(_T0 - timedelta(seconds=60)).isoformat(),
    )
    report = build_operator_automation_status(
        reports_dir=reports,
        now=_T0,
        options=OperatorAutomationStatusOptions(mirror_cooldown_seconds=900),
    )
    assert report["verdict"] == "healthy"
    assert report["dashboard_auto_mirror"]["cooldown_remaining_seconds"] > 0


def test_live_mail_lock(active_current: Path) -> None:
    reports = _healthy_fixture(active_current)
    (active_current / "auto_refresh.lock").write_text(
        json.dumps({"pid": 12345, "started_at": _T0.isoformat()}),
        encoding="utf-8",
    )
    report = build_operator_automation_status(
        reports_dir=reports,
        now=_T0,
        process_alive=lambda pid: pid == 12345,
    )
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "wait_for_running_mail_refresh"


def test_live_mirror_lock(active_current: Path) -> None:
    reports = _healthy_fixture(active_current)
    (active_current / "dashboard_auto_mirror.lock").write_text(
        json.dumps({"pid": 99999, "started_at": _T0.isoformat()}),
        encoding="utf-8",
    )
    report = build_operator_automation_status(
        reports_dir=reports,
        now=_T0,
        process_alive=lambda pid: pid == 99999,
    )
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "wait_for_running_mirror_refresh"


def test_malformed_mail_state(active_current: Path) -> None:
    _write_manifest(active_current)
    (active_current / MAIL_STATE_FILENAME).write_text("{not json", encoding="utf-8")
    _write_mirror_state(active_current)
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "blocked"
    assert report["recommended_action"] == "inspect_logs"


def test_consecutive_failures_blocked(active_current: Path) -> None:
    _write_manifest(active_current)
    _write_mail_state(active_current, consecutive_failures=3)
    _write_mirror_state(active_current)
    report = build_operator_automation_status(
        reports_dir=active_current.parent.parent,
        now=_T0,
    )
    assert report["verdict"] == "blocked"


def test_pause_file(active_current: Path) -> None:
    reports = _healthy_fixture(active_current)
    (active_current / "auto_refresh_paused").write_text("", encoding="utf-8")
    report = build_operator_automation_status(reports_dir=reports, now=_T0)
    assert report["verdict"] == "attention"
    assert report["recommended_action"] == "resume_or_leave_paused"
