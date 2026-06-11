"""Read-only operator automation health for mail refresh + dashboard mirror loops."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.operator_cli.daily_core_manifest import (
    MANIFEST_FILENAME,
    daily_core_run_manifest_path,
)
from origenlab_email_pipeline.operator_cli.dashboard_auto_mirror import (
    DashboardAutoMirrorState,
    DEFAULT_COOLDOWN_SECONDS as MIRROR_DEFAULT_COOLDOWN_SECONDS,
    STATE_FILENAME as MIRROR_STATE_FILENAME,
)
from origenlab_email_pipeline.operator_cli.mail_auto_refresh import (
    DEFAULT_COOLDOWN_SECONDS as MAIL_DEFAULT_COOLDOWN_SECONDS,
    MailAutoRefreshState,
    STATE_FILENAME as MAIL_STATE_FILENAME,
    STALE_LOCK_SECONDS,
    _process_alive,
    read_lock,
)

ProcessAliveFn = Callable[[int], bool]
NowFn = Callable[[], datetime]

VERDICT_HEALTHY = "healthy"
VERDICT_ATTENTION = "attention"
VERDICT_BLOCKED = "blocked"

TRACKED_MAIL_CRON_SCRIPT = "scripts/operator/run_auto_refresh_mail.sh"
TRACKED_MIRROR_CRON_SCRIPT = "scripts/operator/run_auto_mirror_dashboard.sh"
LEGACY_MIRROR_CRON_WRAPPER = "reports/out/active/current/bin/run_auto_mirror_dashboard.sh"
JOINED_FLAG_PATTERN = re.compile(r"--\w+--\w+")

CrontabInspectFn = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class OperatorAutomationStatusOptions:
    json_output: bool = False
    mirror_cooldown_seconds: int = MIRROR_DEFAULT_COOLDOWN_SECONDS
    skip_cron_inspection: bool = False
    cron_note: str | None = None


def _active_current_path(reports_dir: Path | None = None) -> Path:
    base = reports_dir or load_settings().resolved_reports_dir()
    return base / "active" / "current"


def _iso_now(now: datetime) -> str:
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_seconds(ts: str | None, now: datetime) -> int | None:
    parsed = _parse_iso(ts)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _lock_is_live(lock_file: Path, *, process_alive: ProcessAliveFn) -> bool:
    existing = read_lock(lock_file)
    if not existing:
        return False
    return process_alive(int(existing.get("pid") or -1))


def _lock_age_seconds(lock_file: Path, now: datetime) -> int | None:
    existing = read_lock(lock_file)
    if not existing:
        return None
    return _age_seconds(existing.get("started_at"), now)


def _mail_pending(mail_state: MailAutoRefreshState) -> bool:
    return any(
        value is not None
        for value in (
            mail_state.pending_inbox_total,
            mail_state.pending_sent_total,
            mail_state.pending_inbox_max_uid,
            mail_state.pending_sent_max_uid,
        )
    )


def _mirror_matches_daily_core(
    *,
    mirrored_at: str | None,
    daily_core_generated_at: str | None,
) -> bool | None:
    mirrored = _parse_iso(mirrored_at)
    generated = _parse_iso(daily_core_generated_at)
    if mirrored is None or generated is None:
        return None
    return mirrored >= generated


def _cooldown_remaining(last_at: str | None, *, cooldown_seconds: int, now: datetime) -> int:
    elapsed = _age_seconds(last_at, now)
    if elapsed is None:
        return 0
    remaining = cooldown_seconds - elapsed
    return max(0, int(remaining))


def _crontab_active_lines(content: str) -> list[str]:
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _inspect_crontab_content(content: str) -> dict[str, Any]:
    cron_warnings: list[str] = []
    lines = _crontab_active_lines(content)
    joined_flags = any(JOINED_FLAG_PATTERN.search(line) for line in lines)

    mail_entry_present = False
    mirror_entry_present = False
    mail_uses_tracked_script = False
    mirror_uses_tracked_script = False
    legacy_runtime_wrapper_present = False

    for line in lines:
        if "auto-refresh-mail" in line or "run_auto_refresh_mail.sh" in line:
            mail_entry_present = True
        if TRACKED_MAIL_CRON_SCRIPT in line:
            mail_uses_tracked_script = True

        if "auto-mirror-dashboard" in line or "run_auto_mirror_dashboard.sh" in line:
            mirror_entry_present = True
        if LEGACY_MIRROR_CRON_WRAPPER in line or "active/current/bin/run_auto_mirror_dashboard.sh" in line:
            legacy_runtime_wrapper_present = True
        if TRACKED_MIRROR_CRON_SCRIPT in line and LEGACY_MIRROR_CRON_WRAPPER not in line:
            mirror_uses_tracked_script = True

    if joined_flags:
        cron_warnings.append("broken_joined_flags_detected")
    if legacy_runtime_wrapper_present:
        cron_warnings.append("legacy_runtime_mirror_wrapper_detected")

    return {
        "inspected": True,
        "crontab_available": True,
        "mail_entry_present": mail_entry_present,
        "mirror_entry_present": mirror_entry_present,
        "mail_uses_tracked_script": mail_uses_tracked_script,
        "mirror_uses_tracked_script": mirror_uses_tracked_script,
        "legacy_runtime_wrapper_present": legacy_runtime_wrapper_present,
        "broken_joined_flags": joined_flags,
        "warnings": cron_warnings,
    }


def _empty_crontab_inspection(*, warning: str | None = None) -> dict[str, Any]:
    cron_warnings = [warning] if warning else []
    return {
        "inspected": True,
        "crontab_available": True,
        "mail_entry_present": False,
        "mirror_entry_present": False,
        "mail_uses_tracked_script": False,
        "mirror_uses_tracked_script": False,
        "legacy_runtime_wrapper_present": False,
        "broken_joined_flags": False,
        "warnings": cron_warnings,
    }


def read_user_crontab() -> dict[str, Any]:
    """Read the current user's crontab without mutation."""
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return {
            "inspected": True,
            "crontab_available": False,
            "mail_entry_present": False,
            "mirror_entry_present": False,
            "mail_uses_tracked_script": False,
            "mirror_uses_tracked_script": False,
            "legacy_runtime_wrapper_present": False,
            "broken_joined_flags": False,
            "warnings": ["crontab_command_unavailable"],
        }
    except subprocess.TimeoutExpired:
        return _empty_crontab_inspection(warning="crontab_read_timeout")

    stderr = (proc.stderr or "").strip().lower()
    if proc.returncode != 0:
        if "no crontab" in stderr:
            return _empty_crontab_inspection(warning="no_crontab_for_user")
        return {
            "inspected": True,
            "crontab_available": True,
            "mail_entry_present": False,
            "mirror_entry_present": False,
            "mail_uses_tracked_script": False,
            "mirror_uses_tracked_script": False,
            "legacy_runtime_wrapper_present": False,
            "broken_joined_flags": False,
            "warnings": ["crontab_read_failed"],
        }

    return _inspect_crontab_content(proc.stdout or "")


def _apply_cron_verdict_override(
    *,
    verdict: str,
    recommended_action: str,
    cron: dict[str, Any],
    warnings: list[str],
) -> tuple[str, str]:
    if not cron.get("inspected"):
        return verdict, recommended_action
    if verdict != VERDICT_HEALTHY:
        return verdict, recommended_action

    cron_warnings = cron.get("warnings") or []
    for item in cron_warnings:
        if item not in warnings:
            warnings.append(item)

    if cron.get("broken_joined_flags"):
        return VERDICT_ATTENTION, "fix_crontab_spacing"
    if cron.get("legacy_runtime_wrapper_present"):
        return VERDICT_ATTENTION, "migrate_cron_to_tracked_scripts"
    if not cron.get("crontab_available"):
        return verdict, recommended_action
    if not cron.get("mail_entry_present") or not cron.get("mirror_entry_present"):
        return VERDICT_ATTENTION, "inspect_crontab"

    return verdict, recommended_action


def _safe_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "malformed"
    if not isinstance(data, dict):
        return None, "malformed"
    return data, None


def build_operator_automation_status(
    *,
    reports_dir: Path | None = None,
    options: OperatorAutomationStatusOptions | None = None,
    now: datetime | None = None,
    process_alive: ProcessAliveFn | None = None,
    read_crontab: CrontabInspectFn | None = None,
) -> dict[str, Any]:
    opts = options or OperatorAutomationStatusOptions()
    now_dt = now or datetime.now(timezone.utc)
    alive = process_alive or _process_alive
    active_current = _active_current_path(reports_dir)
    warnings: list[str] = []

    manifest_path = daily_core_run_manifest_path(reports_dir)
    manifest_data, manifest_error = _safe_load_json(manifest_path)

    mail_state_path = active_current / MAIL_STATE_FILENAME
    mail_data, mail_error = _safe_load_json(mail_state_path)
    mail_state = MailAutoRefreshState.from_dict(mail_data) if mail_data is not None else None

    mirror_state_path = active_current / MIRROR_STATE_FILENAME
    mirror_data, mirror_error = _safe_load_json(mirror_state_path)
    mirror_state = DashboardAutoMirrorState.from_dict(mirror_data) if mirror_data is not None else None

    mail_pause = (active_current / "auto_refresh_paused").is_file()
    mirror_pause = (active_current / "dashboard_auto_mirror_paused").is_file()
    paused = mail_pause or mirror_pause

    mail_lock_path = active_current / "auto_refresh.lock"
    mirror_lock_path = active_current / "dashboard_auto_mirror.lock"
    mail_lock_live = _lock_is_live(mail_lock_path, process_alive=alive)
    mirror_lock_live = _lock_is_live(mirror_lock_path, process_alive=alive)
    mail_lock_age = _lock_age_seconds(mail_lock_path, now_dt)
    mirror_lock_age = _lock_age_seconds(mirror_lock_path, now_dt)

    daily_core_status = manifest_data.get("status") if manifest_data else None
    daily_core_returncode = manifest_data.get("returncode") if manifest_data else None
    daily_core_generated_at = manifest_data.get("generated_at_utc") if manifest_data else None
    daily_core_steps = len(manifest_data.get("steps") or []) if manifest_data else 0

    mail_dirty = bool(mail_state.dirty) if mail_state else False
    mail_pending = _mail_pending(mail_state) if mail_state else False

    mirror_matches = _mirror_matches_daily_core(
        mirrored_at=mirror_state.last_mirrored_daily_core_generated_at if mirror_state else None,
        daily_core_generated_at=daily_core_generated_at,
    )
    if mirror_matches is None and mirror_state and daily_core_generated_at:
        warnings.append("could_not_compare_mirror_and_daily_core_timestamps")

    mirror_cooldown_remaining = _cooldown_remaining(
        mirror_state.last_successful_mirror_at if mirror_state else None,
        cooldown_seconds=opts.mirror_cooldown_seconds,
        now=now_dt,
    )
    mirror_behind = mirror_matches is False

    daily_core_section: dict[str, Any] = {
        "exists": manifest_data is not None,
        "status": daily_core_status,
        "returncode": daily_core_returncode,
        "generated_at_utc": daily_core_generated_at,
        "age_seconds": _age_seconds(daily_core_generated_at, now_dt),
        "steps": daily_core_steps,
        "parse_error": manifest_error,
    }

    mail_section: dict[str, Any] = {
        "state_exists": mail_data is not None,
        "paused": mail_pause,
        "lock_live": mail_lock_live,
        "lock_age_seconds": mail_lock_age,
        "dirty": mail_dirty,
        "pending": mail_pending,
        "last_result": mail_state.last_result if mail_state else None,
        "last_change_seen_at": mail_state.last_change_seen_at if mail_state else None,
        "last_successful_refresh_at": mail_state.last_successful_refresh_at if mail_state else None,
        "last_run_started_at": mail_state.last_run_started_at if mail_state else None,
        "last_run_finished_at": mail_state.last_run_finished_at if mail_state else None,
        "last_seen_inbox_total": mail_state.last_seen_inbox_total if mail_state else None,
        "last_seen_sent_total": mail_state.last_seen_sent_total if mail_state else None,
        "pending_inbox_total": mail_state.pending_inbox_total if mail_state else None,
        "pending_sent_total": mail_state.pending_sent_total if mail_state else None,
        "pending_inbox_max_uid": mail_state.pending_inbox_max_uid if mail_state else None,
        "pending_sent_max_uid": mail_state.pending_sent_max_uid if mail_state else None,
        "cooldown_seconds_default": MAIL_DEFAULT_COOLDOWN_SECONDS,
        "consecutive_failures": mail_state.consecutive_failures if mail_state else 0,
        "parse_error": mail_error,
    }

    mirror_section: dict[str, Any] = {
        "state_exists": mirror_data is not None,
        "paused": mirror_pause,
        "lock_live": mirror_lock_live,
        "lock_age_seconds": mirror_lock_age,
        "last_result": mirror_state.last_result if mirror_state else None,
        "last_successful_mirror_at": mirror_state.last_successful_mirror_at if mirror_state else None,
        "last_mirrored_daily_core_generated_at": (
            mirror_state.last_mirrored_daily_core_generated_at if mirror_state else None
        ),
        "last_run_started_at": mirror_state.last_run_started_at if mirror_state else None,
        "last_run_finished_at": mirror_state.last_run_finished_at if mirror_state else None,
        "mirror_matches_daily_core": mirror_matches,
        "cooldown_seconds": opts.mirror_cooldown_seconds,
        "cooldown_remaining_seconds": mirror_cooldown_remaining,
        "consecutive_failures": mirror_state.consecutive_failures if mirror_state else 0,
        "parse_error": mirror_error,
    }

    verdict, recommended_action = _derive_verdict_and_action(
        daily_core=daily_core_section,
        mail=mail_section,
        mirror=mirror_section,
        paused=paused,
        mirror_behind=mirror_behind,
        warnings=warnings,
    )

    if opts.skip_cron_inspection:
        cron_section: dict[str, Any] = {
            "note": opts.cron_note or "not inspected by this command",
        }
    else:
        inspect_crontab = read_crontab or read_user_crontab
        cron_section = inspect_crontab()
        verdict, recommended_action = _apply_cron_verdict_override(
            verdict=verdict,
            recommended_action=recommended_action,
            cron=cron_section,
            warnings=warnings,
        )

    return {
        "generated_at_utc": _iso_now(now_dt),
        "active_current_dir": str(active_current),
        "verdict": verdict,
        "daily_core": daily_core_section,
        "mail_auto_refresh": mail_section,
        "dashboard_auto_mirror": mirror_section,
        "cron": cron_section,
        "recommended_action": recommended_action,
        "warnings": warnings,
    }


def _derive_verdict_and_action(
    *,
    daily_core: dict[str, Any],
    mail: dict[str, Any],
    mirror: dict[str, Any],
    paused: bool,
    mirror_behind: bool,
    warnings: list[str],
) -> tuple[str, str]:
    mail_failures = int(mail.get("consecutive_failures") or 0)
    mirror_failures = int(mirror.get("consecutive_failures") or 0)

    if daily_core.get("parse_error") == "malformed":
        return VERDICT_BLOCKED, "inspect_logs"
    if mail.get("parse_error") == "malformed":
        return VERDICT_BLOCKED, "inspect_logs"
    if mirror.get("parse_error") == "malformed":
        return VERDICT_BLOCKED, "inspect_logs"

    if daily_core.get("exists") and (
        daily_core.get("status") != "success" or daily_core.get("returncode") != 0
    ):
        return VERDICT_BLOCKED, "inspect_failed_daily_core"

    if mail_failures >= 3 or mirror_failures >= 3:
        return VERDICT_BLOCKED, "inspect_logs"

    for section, label in ((mail, "mail"), (mirror, "dashboard")):
        if section.get("lock_live") and section.get("lock_age_seconds") is not None:
            if int(section["lock_age_seconds"]) >= STALE_LOCK_SECONDS:
                warnings.append(f"stale_{label}_lock_detected")
                return VERDICT_BLOCKED, "clear_stale_lock_after_manual_review"

    if paused:
        return VERDICT_ATTENTION, "resume_or_leave_paused"

    if mail.get("lock_live"):
        return VERDICT_ATTENTION, "wait_for_running_mail_refresh"
    if mirror.get("lock_live"):
        return VERDICT_ATTENTION, "wait_for_running_mirror_refresh"

    if mail.get("dirty"):
        return VERDICT_ATTENTION, "wait_for_mail_quiet_window"
    if mail.get("pending"):
        return VERDICT_ATTENTION, "wait_for_mail_quiet_window"

    if not daily_core.get("exists"):
        return VERDICT_ATTENTION, "create_missing_state_by_running_dry_run"
    if not mail.get("state_exists"):
        return VERDICT_ATTENTION, "create_missing_state_by_running_dry_run"
    if not mirror.get("state_exists"):
        return VERDICT_ATTENTION, "create_missing_state_by_running_dry_run"

    if mirror_behind:
        if int(mirror.get("cooldown_remaining_seconds") or 0) > 0:
            return VERDICT_ATTENTION, "wait_for_mirror_cooldown"
        return VERDICT_ATTENTION, "run_auto_mirror_dashboard"

    if mail_failures > 0 or mirror_failures > 0:
        return VERDICT_ATTENTION, "inspect_logs"

    healthy_checks = (
        daily_core.get("status") == "success",
        daily_core.get("returncode") == 0,
        mail.get("dirty") is False,
        mail.get("pending") is False,
        not mail.get("lock_live"),
        not mirror.get("lock_live"),
        mirror.get("mirror_matches_daily_core") is True,
        mail_failures == 0,
        mirror_failures == 0,
    )
    if all(healthy_checks):
        return VERDICT_HEALTHY, "none"

    return VERDICT_ATTENTION, "inspect_logs"


def _fmt_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def format_operator_automation_status_text(report: dict[str, Any]) -> str:
    lines = [
        "operator_automation_status",
        f"verdict={report['verdict']}",
        f"generated_at_utc={report['generated_at_utc']}",
        f"active_current_dir={report['active_current_dir']}",
        "",
        "daily_core",
    ]
    dc = report["daily_core"]
    for key in ("status", "returncode", "generated_at_utc", "age_seconds", "steps"):
        lines.append(f"  {key}={_fmt_value(dc.get(key))}")

    lines.append("")
    lines.append("mail_auto_refresh")
    mail = report["mail_auto_refresh"]
    for key in (
        "state_exists",
        "paused",
        "lock_live",
        "dirty",
        "pending",
        "last_result",
        "last_change_seen_at",
        "last_successful_refresh_at",
        "last_run_started_at",
        "last_run_finished_at",
        "last_seen_inbox_total",
        "last_seen_sent_total",
        "pending_inbox_total",
        "pending_sent_total",
        "consecutive_failures",
    ):
        lines.append(f"  {key}={_fmt_value(mail.get(key))}")

    lines.append("")
    lines.append("dashboard_auto_mirror")
    mirror = report["dashboard_auto_mirror"]
    for key in (
        "state_exists",
        "paused",
        "lock_live",
        "last_result",
        "last_successful_mirror_at",
        "last_mirrored_daily_core_generated_at",
        "mirror_matches_daily_core",
        "cooldown_seconds",
        "cooldown_remaining_seconds",
        "consecutive_failures",
    ):
        lines.append(f"  {key}={_fmt_value(mirror.get(key))}")

    lines.append("")
    lines.append("cron")
    cron = report["cron"]
    if cron.get("note") is not None:
        lines.append(f"  note={cron['note']}")
    else:
        for key in (
            "inspected",
            "crontab_available",
            "mail_entry_present",
            "mirror_entry_present",
            "mail_uses_tracked_script",
            "mirror_uses_tracked_script",
            "legacy_runtime_wrapper_present",
            "broken_joined_flags",
        ):
            if key in cron:
                lines.append(f"  {key}={_fmt_value(cron.get(key))}")
        if cron.get("warnings"):
            lines.append(f"  warnings={','.join(cron['warnings'])}")
    lines.append("")
    lines.append(f"recommended_action={report['recommended_action']}")
    if report.get("warnings"):
        lines.append(f"warnings={','.join(report['warnings'])}")
    return "\n".join(lines) + "\n"


def run_operator_automation_status(
    options: OperatorAutomationStatusOptions | None = None,
    *,
    reports_dir: Path | None = None,
    process_alive: ProcessAliveFn | None = None,
    now: datetime | None = None,
    read_crontab: CrontabInspectFn | None = None,
) -> int:
    report = build_operator_automation_status(
        reports_dir=reports_dir,
        options=options,
        now=now,
        process_alive=process_alive,
        read_crontab=read_crontab,
    )
    if options and options.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_operator_automation_status_text(report), end="")
    if report["verdict"] == VERDICT_BLOCKED:
        return 2
    if report["verdict"] == VERDICT_ATTENTION:
        return 1
    return 0


def parse_operator_automation_status_args(argv: list[str]) -> OperatorAutomationStatusOptions:
    import argparse

    parser = argparse.ArgumentParser(prog="operator-automation-status", add_help=True)
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    parser.add_argument(
        "--cooldown-seconds",
        type=int,
        default=MIRROR_DEFAULT_COOLDOWN_SECONDS,
        help="Dashboard mirror cooldown for remaining-seconds calculation",
    )
    parser.add_argument(
        "--skip-cron-inspection",
        action="store_true",
        help="Do not read user crontab (preserves legacy cron output)",
    )
    ns = parser.parse_args(argv)
    return OperatorAutomationStatusOptions(
        json_output=ns.json,
        mirror_cooldown_seconds=ns.cooldown_seconds,
        skip_cron_inspection=ns.skip_cron_inspection,
    )


def print_operator_automation_status_help() -> None:
    print(
        "operator-automation-status — read-only health for automation loops A and B\n\n"
        "  uv run origenlab operator-automation-status\n"
        "  uv run origenlab operator-automation-status --json\n"
        "  uv run origenlab operator-automation-status --skip-cron-inspection\n\n"
        "Inspects local state files and user crontab read-only (no Gmail, Postgres, daily-core, "
        "or mirror writes).\n"
    )
