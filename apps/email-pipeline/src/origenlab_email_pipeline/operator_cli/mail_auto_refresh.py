"""Debounced mailbox auto-refresh — coalesce INBOX/SENT changes before daily-core."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.operator_cli.mailbox_probe import MailboxSnapshot, probe_mailbox_snapshot
from origenlab_email_pipeline.operator_cli.refresh import RefreshDashboardOptions, run_daily_core

STATE_FILENAME = "mail_auto_refresh_state.json"
LOCK_FILENAME = "auto_refresh.lock"
PAUSE_FILENAME = "auto_refresh_paused"
STATE_SCHEMA_VERSION = 1
STALE_LOCK_SECONDS = 2 * 60 * 60

DEFAULT_QUIET_SECONDS = 180
DEFAULT_COOLDOWN_SECONDS = 600
DEFAULT_LARGE_SENT_DELTA = 50
DEFAULT_LARGE_SENT_QUIET_SECONDS = 900

MailboxProbeFn = Callable[[], MailboxSnapshot]
DailyCoreRunnerFn = Callable[[], int]
NowFn = Callable[[], datetime]


@dataclass(frozen=True)
class MailAutoRefreshOptions:
    apply: bool = False
    once: bool = True
    daemon: bool = False
    interval_seconds: int = 120
    quiet_seconds: int = DEFAULT_QUIET_SECONDS
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
    large_sent_delta: int = DEFAULT_LARGE_SENT_DELTA
    large_sent_quiet_seconds: int = DEFAULT_LARGE_SENT_QUIET_SECONDS


@dataclass
class MailAutoRefreshState:
    schema_version: int = STATE_SCHEMA_VERSION
    last_seen_inbox_total: int | None = None
    last_seen_sent_total: int | None = None
    last_seen_inbox_max_uid: int | None = None
    last_seen_sent_max_uid: int | None = None
    last_change_seen_at: str | None = None
    last_successful_refresh_at: str | None = None
    last_run_started_at: str | None = None
    last_run_finished_at: str | None = None
    last_result: str | None = None
    consecutive_failures: int = 0
    dirty: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailAutoRefreshState:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: data[k] for k in data if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MailAutoRefreshResult:
    apply: bool
    changed: bool
    dirty: bool
    reason: str
    inbox_total: int
    sent_total: int
    inbox_delta: int
    sent_delta: int
    quiet_seconds: int
    cooldown_seconds: int
    should_run: bool
    ran_daily_core: bool
    daily_core_returncode: int | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def output_lines(self) -> list[str]:
        lines = [
            "mail_auto_refresh",
            f"apply={'true' if self.apply else 'false'}",
            f"changed={'true' if self.changed else 'false'}",
            f"dirty={'true' if self.dirty else 'false'}",
            f"reason={self.reason}",
            f"inbox_total={self.inbox_total}",
            f"sent_total={self.sent_total}",
            f"inbox_delta={self.inbox_delta}",
            f"sent_delta={self.sent_delta}",
            f"quiet_seconds={self.quiet_seconds}",
            f"cooldown_seconds={self.cooldown_seconds}",
            f"should_run={'true' if self.should_run else 'false'}",
            f"ran_daily_core={'true' if self.ran_daily_core else 'false'}",
        ]
        if self.daily_core_returncode is not None:
            lines.append(f"daily_core_returncode={self.daily_core_returncode}")
        for key, value in sorted(self.extra.items()):
            lines.append(f"{key}={value}")
        return lines


def active_current_dir(reports_dir: Path | None = None) -> Path:
    base = reports_dir or load_settings().resolved_reports_dir()
    path = base / "active" / "current"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(reports_dir: Path | None = None) -> Path:
    return active_current_dir(reports_dir) / STATE_FILENAME


def lock_path(reports_dir: Path | None = None) -> Path:
    return active_current_dir(reports_dir) / LOCK_FILENAME


def pause_path(reports_dir: Path | None = None) -> Path:
    return active_current_dir(reports_dir) / PAUSE_FILENAME


def load_state(path: Path) -> MailAutoRefreshState:
    if not path.is_file():
        return MailAutoRefreshState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return MailAutoRefreshState.from_dict(data)


def save_state(path: Path, state: MailAutoRefreshState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iso_now(now: datetime) -> str:
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _seconds_since(ts: str | None, now: datetime) -> float | None:
    parsed = _parse_iso(ts)
    if parsed is None:
        return None
    return (now - parsed).total_seconds()


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_lock(lock_file: Path) -> dict[str, Any] | None:
    if not lock_file.is_file():
        return None
    try:
        return json.loads(lock_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"pid": -1, "started_at": None}


def acquire_lock(lock_file: Path, *, now: datetime, stale_seconds: int = STALE_LOCK_SECONDS) -> tuple[bool, str]:
    existing = read_lock(lock_file)
    if existing:
        pid = int(existing.get("pid") or -1)
        if _process_alive(pid):
            return False, "already_running"
        started_at = existing.get("started_at")
        age = _seconds_since(started_at, now) if started_at else None
        if age is not None and age >= stale_seconds:
            print(
                f"warning: clearing stale auto-refresh lock (age_seconds={int(age)})",
                flush=True,
            )
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pid": os.getpid(), "started_at": _iso_now(now)}
    lock_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True, "acquired"


def release_lock(lock_file: Path) -> None:
    if lock_file.is_file():
        lock_file.unlink(missing_ok=True)


def _mailbox_changed(state: MailAutoRefreshState, snapshot: MailboxSnapshot) -> bool:
    if state.last_seen_inbox_total is None and state.last_seen_sent_total is None:
        return False
    if snapshot.inbox_total != state.last_seen_inbox_total:
        return True
    if snapshot.sent_total != state.last_seen_sent_total:
        return True
    if state.last_seen_inbox_max_uid is not None and snapshot.inbox.max_uid != state.last_seen_inbox_max_uid:
        return True
    if state.last_seen_sent_max_uid is not None and snapshot.sent.max_uid != state.last_seen_sent_max_uid:
        return True
    return False


def _effective_quiet_seconds(
    *,
    sent_delta: int,
    options: MailAutoRefreshOptions,
) -> int:
    if sent_delta > options.large_sent_delta:
        return options.large_sent_quiet_seconds
    return options.quiet_seconds


def evaluate_mail_auto_refresh(
    *,
    snapshot: MailboxSnapshot,
    state: MailAutoRefreshState,
    options: MailAutoRefreshOptions,
    now: datetime,
) -> tuple[MailAutoRefreshState, MailAutoRefreshResult]:
    inbox_total = snapshot.inbox_total
    sent_total = snapshot.sent_total
    baseline = state.last_seen_inbox_total is None and state.last_seen_sent_total is None

    if baseline:
        state.last_seen_inbox_total = inbox_total
        state.last_seen_sent_total = sent_total
        state.last_seen_inbox_max_uid = snapshot.inbox.max_uid
        state.last_seen_sent_max_uid = snapshot.sent.max_uid
        state.dirty = False
        quiet = options.quiet_seconds
        return state, MailAutoRefreshResult(
            apply=options.apply,
            changed=False,
            dirty=False,
            reason="baseline_established",
            inbox_total=inbox_total,
            sent_total=sent_total,
            inbox_delta=0,
            sent_delta=0,
            quiet_seconds=quiet,
            cooldown_seconds=options.cooldown_seconds,
            should_run=False,
            ran_daily_core=False,
        )

    inbox_delta = inbox_total - int(state.last_seen_inbox_total or 0)
    sent_delta = sent_total - int(state.last_seen_sent_total or 0)
    changed = _mailbox_changed(state, snapshot)
    quiet_seconds = _effective_quiet_seconds(sent_delta=sent_delta, options=options)

    if changed:
        if not state.dirty or state.last_change_seen_at is None:
            state.dirty = True
            state.last_change_seen_at = _iso_now(now)
        reason = "change_detected"
    elif state.dirty:
        reason = "debouncing"
    else:
        reason = "no_change"

    quiet_elapsed = _seconds_since(state.last_change_seen_at, now) if state.dirty else None
    quiet_passed = state.dirty and quiet_elapsed is not None and quiet_elapsed >= quiet_seconds

    cooldown_elapsed = _seconds_since(state.last_successful_refresh_at, now)
    cooldown_passed = cooldown_elapsed is None or cooldown_elapsed >= options.cooldown_seconds

    if state.dirty and not quiet_passed:
        reason = "debouncing"
    elif state.dirty and quiet_passed and not cooldown_passed:
        reason = "cooldown"
    elif state.dirty and quiet_passed and cooldown_passed and not options.apply:
        reason = "dry_run"

    should_run = bool(
        options.apply and state.dirty and quiet_passed and cooldown_passed
    )

    return state, MailAutoRefreshResult(
        apply=options.apply,
        changed=changed,
        dirty=state.dirty,
        reason=reason,
        inbox_total=inbox_total,
        sent_total=sent_total,
        inbox_delta=inbox_delta,
        sent_delta=sent_delta,
        quiet_seconds=quiet_seconds,
        cooldown_seconds=options.cooldown_seconds,
        should_run=should_run,
        ran_daily_core=False,
    )


def run_mail_auto_refresh(
    options: MailAutoRefreshOptions,
    *,
    reports_dir: Path | None = None,
    probe: MailboxProbeFn | None = None,
    run_daily_core_fn: DailyCoreRunnerFn | None = None,
    now_fn: NowFn | None = None,
) -> int:
    if options.daemon:
        raise ValueError(
            "auto-refresh-mail --daemon is not implemented yet; use --once with an external scheduler "
            "(cron/systemd timer every few minutes)."
        )
    if not options.once:
        raise ValueError("auto-refresh-mail requires --once (daemon mode not implemented yet).")

    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    pause_file = pause_path(reports_dir)
    if pause_file.is_file():
        result = MailAutoRefreshResult(
            apply=options.apply,
            changed=False,
            dirty=False,
            reason="paused",
            inbox_total=0,
            sent_total=0,
            inbox_delta=0,
            sent_delta=0,
            quiet_seconds=options.quiet_seconds,
            cooldown_seconds=options.cooldown_seconds,
            should_run=False,
            ran_daily_core=False,
        )
        for line in result.output_lines():
            print(line)
        return 0

    lock_file = lock_path(reports_dir)
    acquired, lock_reason = acquire_lock(lock_file, now=now)
    if not acquired:
        result = MailAutoRefreshResult(
            apply=options.apply,
            changed=False,
            dirty=False,
            reason=lock_reason,
            inbox_total=0,
            sent_total=0,
            inbox_delta=0,
            sent_delta=0,
            quiet_seconds=options.quiet_seconds,
            cooldown_seconds=options.cooldown_seconds,
            should_run=False,
            ran_daily_core=False,
        )
        for line in result.output_lines():
            print(line)
        return 0

    state_file = state_path(reports_dir)
    state = load_state(state_file)
    state.last_run_started_at = _iso_now(now)

    try:
        snapshot = (probe or probe_mailbox_snapshot)()
        state, result = evaluate_mail_auto_refresh(
            snapshot=snapshot,
            state=state,
            options=options,
            now=now,
        )

        daily_core_rc: int | None = None
        if result.should_run:
            runner = run_daily_core_fn or (
                lambda: run_daily_core(RefreshDashboardOptions(apply=True, no_mirror=True))
            )
            daily_core_rc = runner()
            result.ran_daily_core = True
            result.daily_core_returncode = daily_core_rc
            finished = (now_fn or (lambda: datetime.now(timezone.utc)))()
            state.last_run_finished_at = _iso_now(finished)
            if daily_core_rc == 0:
                state.last_successful_refresh_at = state.last_run_finished_at
                state.last_seen_inbox_total = snapshot.inbox_total
                state.last_seen_sent_total = snapshot.sent_total
                state.last_seen_inbox_max_uid = snapshot.inbox.max_uid
                state.last_seen_sent_max_uid = snapshot.sent.max_uid
                state.dirty = False
                state.last_change_seen_at = None
                state.consecutive_failures = 0
                state.last_result = "success"
                result.dirty = False
                result.reason = "refreshed"
            else:
                state.consecutive_failures += 1
                state.last_result = "daily_core_failed"
                result.reason = "daily_core_failed"
        else:
            state.last_run_finished_at = _iso_now(
                (now_fn or (lambda: datetime.now(timezone.utc)))()
            )
            state.last_result = result.reason

        save_state(state_file, state)
        for line in result.output_lines():
            print(line)
        if daily_core_rc is not None and daily_core_rc != 0:
            return daily_core_rc
        return 0
    finally:
        release_lock(lock_file)


def parse_mail_auto_refresh_args(argv: list[str]) -> MailAutoRefreshOptions:
    import argparse

    parser = argparse.ArgumentParser(prog="auto-refresh-mail", add_help=True)
    parser.add_argument("--apply", action="store_true", help="Run daily-core --apply when gates pass")
    parser.add_argument("--once", action="store_true", help="Single evaluation (required)")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Loop mode (not implemented — use external scheduler with --once)",
    )
    parser.add_argument("--interval-seconds", type=int, default=120)
    parser.add_argument("--quiet-seconds", type=int, default=DEFAULT_QUIET_SECONDS)
    parser.add_argument("--cooldown-seconds", type=int, default=DEFAULT_COOLDOWN_SECONDS)
    parser.add_argument("--large-sent-delta", type=int, default=DEFAULT_LARGE_SENT_DELTA)
    parser.add_argument(
        "--large-sent-quiet-seconds",
        type=int,
        default=DEFAULT_LARGE_SENT_QUIET_SECONDS,
    )
    ns = parser.parse_args(argv)
    if not ns.once and not ns.daemon:
        parser.error("--once is required (daemon mode not implemented yet)")
    return MailAutoRefreshOptions(
        apply=ns.apply,
        once=ns.once,
        daemon=ns.daemon,
        interval_seconds=ns.interval_seconds,
        quiet_seconds=ns.quiet_seconds,
        cooldown_seconds=ns.cooldown_seconds,
        large_sent_delta=ns.large_sent_delta,
        large_sent_quiet_seconds=ns.large_sent_quiet_seconds,
    )


def print_mail_auto_refresh_help() -> None:
    print(
        "auto-refresh-mail — debounced mailbox change detector for daily-core\n\n"
        "  uv run origenlab auto-refresh-mail --once              # dry-run / status (default)\n"
        "  uv run origenlab auto-refresh-mail --once --apply      # run daily-core when gates pass\n\n"
        "Coalesces INBOX/SENT UID-count changes before daily-core. "
        "See docs/pipeline/MAIL_AUTO_REFRESH.md.\n"
    )
