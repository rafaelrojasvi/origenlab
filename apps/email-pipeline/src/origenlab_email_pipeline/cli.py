"""Unified operator CLI — thin wrapper around existing QA scripts (Phase 6B / 6D / 7A).

Does not change script behavior; forwards argv via subprocess after optional ``--``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

GMAIL_INGEST_SCRIPT = "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py"
GMAIL_INGEST_INBOX_FOLDER = "INBOX"
GMAIL_INGEST_SENT_FOLDER = "[Gmail]/Enviados"

# Subcommand -> script path relative to apps/email-pipeline repo root (1:1 wrappers).
SUBCOMMAND_SCRIPTS: dict[str, str] = {
    "status": "scripts/qa/operator_status.py",
    "daily-health": "scripts/qa/run_daily_health_report.py",
    "refresh-safety": "scripts/qa/refresh_outbound_safety_memory.py",
    "validate-csvs": "scripts/qa/validate_campaign_csvs.py",
    "check-readiness": "scripts/qa/check_outbound_readiness.py",
    "post-send-digest": "scripts/qa/build_post_send_digest.py",
    "export-dnr": "scripts/qa/export_do_not_repeat_master.py",
    "ndr-review": "scripts/qa/build_ndr_review_queue.py",
    "audit-overlap": "scripts/qa/export_contacted_lead_overlap_audit.py",
    "build-mart": "scripts/mart/build_business_mart.py",
    "gmail-ingest-help": GMAIL_INGEST_SCRIPT,
}

# Multi-step or special ingest wrappers (not 1:1 SUBCOMMAND_SCRIPTS).
GMAIL_INGEST_COMMANDS: frozenset[str] = frozenset({"gmail-ingest", "gmail-ingest-folders"})

CLI_COMMAND_NAMES: tuple[str, ...] = tuple(SUBCOMMAND_SCRIPTS.keys()) + tuple(
    sorted(GMAIL_INGEST_COMMANDS)
)

# Subcommands that only run the target script ``--help`` (no passthrough).
HELP_ONLY_SUBCOMMANDS: frozenset[str] = frozenset({"gmail-ingest-help"})

_SUBCOMMAND_HELP: dict[str, str] = {
    "status": "Operator READY / CAUTION / BLOCKED snapshot (operator_status.py)",
    "daily-health": "Combined daily health report (run_daily_health_report.py)",
    "refresh-safety": "Outbound safety memory refresh chain (refresh_outbound_safety_memory.py)",
    "validate-csvs": "Campaign CSV contract validation (validate_campaign_csvs.py)",
    "check-readiness": "Outbound readiness checks (check_outbound_readiness.py)",
    "post-send-digest": "Post-send digest artifacts (build_post_send_digest.py)",
    "export-dnr": "Export do-not-repeat master lists (export_do_not_repeat_master.py)",
    "ndr-review": "NDR human-review batches — read-only (build_ndr_review_queue.py)",
    "audit-overlap": "Contacted-lead overlap audit CSV (export_contacted_lead_overlap_audit.py)",
    "build-mart": (
        "Business mart rebuild (build_business_mart.py) — break-glass: optional --rebuild deletes mart tables"
    ),
    "gmail-ingest": (
        "Safe daily Gmail ingest: INBOX then Sent ([Gmail]/Enviados), --skip-duplicate-message-id; "
        "rejects --replace-source"
    ),
    "gmail-ingest-folders": (
        "List IMAP folder labels on the ingest script (use if [Gmail]/Enviados differs)"
    ),
    "gmail-ingest-help": (
        "Show Gmail Workspace ingest --help only. For daily ingest use gmail-ingest."
    ),
}


def repo_root() -> Path:
    """apps/email-pipeline directory (parent of ``src/``)."""
    return Path(__file__).resolve().parents[2]


def gmail_ingest_script_path() -> Path:
    return repo_root() / GMAIL_INGEST_SCRIPT


def script_path_for(subcommand: str) -> Path:
    rel = SUBCOMMAND_SCRIPTS[subcommand]
    return repo_root() / rel


def normalize_passthrough_args(argv: list[str]) -> list[str]:
    """Drop a leading ``--`` separator used between wrapper and script flags."""
    if argv and argv[0] == "--":
        return argv[1:]
    return list(argv)


def validate_gmail_ingest_passthrough(passthrough: list[str] | None) -> list[str]:
    """Return normalized passthrough or raise ValueError if unsafe for gmail-ingest."""
    args = normalize_passthrough_args(passthrough or [])
    if "--replace-source" in args:
        raise ValueError(
            "gmail-ingest does not allow --replace-source (break-glass folder rebuild). "
            "Run scripts/ingest/05_workspace_gmail_imap_to_sqlite.py directly if intentional."
        )
    return args


def build_gmail_ingest_argv_list(passthrough: list[str] | None = None) -> list[list[str]]:
    """Build argv for INBOX then Sent ingest (no subprocess)."""
    extra = validate_gmail_ingest_passthrough(passthrough)
    script = str(gmail_ingest_script_path())
    skip = ["--skip-duplicate-message-id"]
    return [
        [sys.executable, script, "--folder", GMAIL_INGEST_INBOX_FOLDER, *skip, *extra],
        [sys.executable, script, "--folder", GMAIL_INGEST_SENT_FOLDER, *skip, *extra],
    ]


def build_gmail_ingest_folders_argv() -> list[str]:
    return [sys.executable, str(gmail_ingest_script_path()), "--list-folders"]


def build_subcommand_argv(subcommand: str, passthrough: list[str] | None = None) -> list[str]:
    """Build argv for subprocess without executing."""
    if subcommand == "gmail-ingest":
        raise ValueError("use build_gmail_ingest_argv_list() for gmail-ingest")
    if subcommand == "gmail-ingest-folders":
        return build_gmail_ingest_folders_argv()
    script = script_path_for(subcommand)
    if subcommand in HELP_ONLY_SUBCOMMANDS:
        return [sys.executable, str(script), "--help"]
    return [sys.executable, str(script), *normalize_passthrough_args(passthrough or [])]


def run_gmail_ingest(passthrough: list[str] | None = None) -> int:
    """Run INBOX then Sent ingest; stop on first non-zero exit."""
    cwd = str(repo_root())
    for cmd in build_gmail_ingest_argv_list(passthrough):
        proc = subprocess.run(cmd, cwd=cwd, check=False)
        if proc.returncode != 0:
            return int(proc.returncode)
    return 0


def run_subcommand(subcommand: str, passthrough: list[str] | None = None) -> int:
    if subcommand == "gmail-ingest":
        return run_gmail_ingest(passthrough)
    if subcommand == "gmail-ingest-folders":
        proc = subprocess.run(build_gmail_ingest_folders_argv(), cwd=str(repo_root()), check=False)
        return int(proc.returncode)
    cmd = build_subcommand_argv(subcommand, passthrough)
    proc = subprocess.run(cmd, cwd=str(repo_root()), check=False)
    return int(proc.returncode)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="origenlab-email-pipeline",
        description="Operator CLI wrapper — delegates to existing scripts under scripts/.",
        epilog=(
            "Pass script-specific flags after ``--``. Example: "
            "origenlab status -- --json. "
            "gmail-ingest: safe INBOX + Sent ingest (--replace-source rejected). "
            "gmail-ingest-help: ingest --help only."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name in CLI_COMMAND_NAMES:
        script_rel = SUBCOMMAND_SCRIPTS.get(name, GMAIL_INGEST_SCRIPT)
        sub.add_parser(
            name,
            help=_SUBCOMMAND_HELP.get(name, script_rel),
            description=f"Run {script_rel}" if name in SUBCOMMAND_SCRIPTS else _SUBCOMMAND_HELP.get(name, ""),
        )
    return parser


def _is_known_command(command: str) -> bool:
    return command in SUBCOMMAND_SCRIPTS or command in GMAIL_INGEST_COMMANDS


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    command = argv[0]
    if not _is_known_command(command):
        parser.error(f"unknown command {command!r}")

    passthrough = normalize_passthrough_args(argv[1:])
    if command in HELP_ONLY_SUBCOMMANDS and passthrough:
        parser.error(
            f"{command!r} does not accept extra arguments (runs ingest --help only). "
            "Use gmail-ingest for daily INBOX + Sent refresh."
        )
    if command == "gmail-ingest-folders" and passthrough:
        parser.error(
            f"{command!r} does not accept extra arguments (runs ingest --list-folders only)."
        )
    if command == "gmail-ingest":
        try:
            validate_gmail_ingest_passthrough(passthrough)
        except ValueError as exc:
            parser.error(str(exc))

    return run_subcommand(command, passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
