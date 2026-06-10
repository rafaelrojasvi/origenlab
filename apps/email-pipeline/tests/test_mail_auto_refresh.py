"""Tests for debounced mailbox auto-refresh (mocked probe + daily-core)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from origenlab_email_pipeline.operator_cli.mail_auto_refresh import (
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_LARGE_SENT_QUIET_SECONDS,
    DEFAULT_QUIET_SECONDS,
    MailAutoRefreshOptions,
    MailAutoRefreshState,
    acquire_lock,
    evaluate_mail_auto_refresh,
    load_state,
    pause_path,
    run_mail_auto_refresh,
    state_path,
)
from origenlab_email_pipeline.operator_cli.mailbox_probe import (
    MailboxFolderSnapshot,
    MailboxSnapshot,
)

_T0 = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def _snapshot(
    *,
    inbox: int = 100,
    sent: int = 50,
    inbox_max: int | None = 1000,
    sent_max: int | None = 500,
) -> MailboxSnapshot:
    return MailboxSnapshot(
        inbox=MailboxFolderSnapshot("INBOX", inbox, inbox_max),
        sent=MailboxFolderSnapshot("[Gmail]/Enviados", sent, sent_max),
        probed_at_utc=_T0.isoformat(),
    )


def _opts(**kwargs: object) -> MailAutoRefreshOptions:
    return MailAutoRefreshOptions(once=True, **kwargs)


def _baseline_state(
    *,
    inbox: int = 100,
    sent: int = 50,
    inbox_max: int | None = 1000,
    sent_max: int | None = 500,
) -> MailAutoRefreshState:
    return MailAutoRefreshState(
        last_seen_inbox_total=inbox,
        last_seen_sent_total=sent,
        last_seen_inbox_max_uid=inbox_max,
        last_seen_sent_max_uid=sent_max,
    )


def _parse_output(out: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in out.strip().splitlines():
        if "=" in line and line != "mail_auto_refresh":
            key, value = line.split("=", 1)
            result[key] = value
    return result


@pytest.fixture
def reports_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_no_change_does_not_run(reports_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state_file = state_path(reports_dir)
    save = _baseline_state()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(save.to_dict()), encoding="utf-8")
    daily_calls: list[str] = []

    run_mail_auto_refresh(
        _opts(),
        reports_dir=reports_dir,
        probe=lambda: _snapshot(),
        run_daily_core_fn=lambda: daily_calls.append("ran") or 0,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["changed"] == "false"
    assert out["should_run"] == "false"
    assert out["ran_daily_core"] == "false"
    assert out["reason"] == "no_change"
    assert daily_calls == []


def test_first_change_marks_dirty_and_debounces(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_file = state_path(reports_dir)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(_baseline_state().to_dict()), encoding="utf-8")
    daily_calls: list[str] = []

    run_mail_auto_refresh(
        _opts(),
        reports_dir=reports_dir,
        probe=lambda: _snapshot(inbox=101),
        run_daily_core_fn=lambda: daily_calls.append("ran") or 0,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["changed"] == "true"
    assert out["dirty"] == "true"
    assert out["should_run"] == "false"
    assert out["ran_daily_core"] == "false"
    assert out["reason"] == "debouncing"
    assert daily_calls == []
    state = load_state(state_file)
    assert state.dirty is True
    assert state.last_change_seen_at is not None


def test_quiet_window_passed_with_apply_runs_daily_core(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_file = state_path(reports_dir)
    dirty = _baseline_state()
    dirty.dirty = True
    dirty.last_change_seen_at = (_T0 - timedelta(seconds=DEFAULT_QUIET_SECONDS + 5)).isoformat()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(dirty.to_dict()), encoding="utf-8")
    daily_calls: list[str] = []

    rc = run_mail_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        probe=lambda: _snapshot(inbox=101),
        run_daily_core_fn=lambda: daily_calls.append("ran") or 0,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert rc == 0
    assert out["should_run"] == "true"
    assert out["ran_daily_core"] == "true"
    assert out["daily_core_returncode"] == "0"
    assert daily_calls == ["ran"]
    state = load_state(state_file)
    assert state.dirty is False
    assert state.last_successful_refresh_at is not None


def test_cooldown_prevents_repeated_run(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_file = state_path(reports_dir)
    dirty = _baseline_state()
    dirty.dirty = True
    dirty.last_change_seen_at = (_T0 - timedelta(seconds=DEFAULT_QUIET_SECONDS + 5)).isoformat()
    dirty.last_successful_refresh_at = (_T0 - timedelta(seconds=30)).isoformat()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(dirty.to_dict()), encoding="utf-8")

    run_mail_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        probe=lambda: _snapshot(inbox=101),
        run_daily_core_fn=lambda: pytest.fail("daily-core must not run during cooldown"),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["should_run"] == "false"
    assert out["ran_daily_core"] == "false"
    assert out["reason"] == "cooldown"


def test_large_sent_delta_uses_longer_quiet_window(reports_dir: Path) -> None:
    state = _baseline_state(sent=50)
    state.dirty = True
    state.last_change_seen_at = (_T0 - timedelta(seconds=800)).isoformat()
    options = _opts(
        large_sent_delta=50,
        large_sent_quiet_seconds=DEFAULT_LARGE_SENT_QUIET_SECONDS,
    )
    _, result = evaluate_mail_auto_refresh(
        snapshot=_snapshot(sent=120),
        state=state,
        options=options,
        now=_T0,
    )
    assert result.sent_delta == 70
    assert result.quiet_seconds == DEFAULT_LARGE_SENT_QUIET_SECONDS
    assert result.should_run is False
    assert result.reason == "debouncing"


def test_lock_prevents_concurrent_run(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.mail_auto_refresh._process_alive",
        lambda pid: True,
    )
    acquired, _ = acquire_lock(
        reports_dir / "active" / "current" / "auto_refresh.lock",
        now=_T0,
    )
    assert acquired is True

    run_mail_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        probe=lambda: pytest.fail("probe must not run when lock held"),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["reason"] == "already_running"
    assert out["ran_daily_core"] == "false"


def test_pause_file_prevents_run(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pause = pause_path(reports_dir)
    pause.parent.mkdir(parents=True, exist_ok=True)
    pause.write_text("", encoding="utf-8")

    run_mail_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        probe=lambda: pytest.fail("probe must not run when paused"),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["reason"] == "paused"
    assert out["ran_daily_core"] == "false"


def test_dry_run_never_runs_daily_core(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_file = state_path(reports_dir)
    dirty = _baseline_state()
    dirty.dirty = True
    dirty.last_change_seen_at = (_T0 - timedelta(seconds=DEFAULT_QUIET_SECONDS + 5)).isoformat()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(dirty.to_dict()), encoding="utf-8")

    run_mail_auto_refresh(
        _opts(apply=False),
        reports_dir=reports_dir,
        probe=lambda: _snapshot(inbox=101),
        run_daily_core_fn=lambda: pytest.fail("daily-core must not run in dry-run"),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["apply"] == "false"
    assert out["should_run"] == "false"
    assert out["ran_daily_core"] == "false"
    assert out["reason"] == "dry_run"


def test_baseline_established_on_first_run(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_mail_auto_refresh(
        _opts(),
        reports_dir=reports_dir,
        probe=lambda: _snapshot(inbox=200, sent=80),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["reason"] == "baseline_established"
    state = load_state(state_path(reports_dir))
    assert state.last_seen_inbox_total == 200
    assert state.last_seen_sent_total == 80
