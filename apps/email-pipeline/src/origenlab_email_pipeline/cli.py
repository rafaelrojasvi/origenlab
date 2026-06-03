"""Unified operator CLI — thin wrapper around existing QA scripts (Phase 6B).

Does not change script behavior; forwards argv via subprocess after optional ``--``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Subcommand -> script path relative to apps/email-pipeline repo root.
SUBCOMMAND_SCRIPTS: dict[str, str] = {
    "status": "scripts/qa/operator_status.py",
    "daily-health": "scripts/qa/run_daily_health_report.py",
    "refresh-safety": "scripts/qa/refresh_outbound_safety_memory.py",
    "validate-csvs": "scripts/qa/validate_campaign_csvs.py",
    "check-readiness": "scripts/qa/check_outbound_readiness.py",
    "post-send-digest": "scripts/qa/build_post_send_digest.py",
}

_SUBCOMMAND_HELP: dict[str, str] = {
    "status": "Operator READY / CAUTION / BLOCKED snapshot (operator_status.py)",
    "daily-health": "Combined daily health report (run_daily_health_report.py)",
    "refresh-safety": "Outbound safety memory refresh chain (refresh_outbound_safety_memory.py)",
    "validate-csvs": "Campaign CSV contract validation (validate_campaign_csvs.py)",
    "check-readiness": "Outbound readiness checks (check_outbound_readiness.py)",
    "post-send-digest": "Post-send digest artifacts (build_post_send_digest.py)",
}


def repo_root() -> Path:
    """apps/email-pipeline directory (parent of ``src/``)."""
    return Path(__file__).resolve().parents[2]


def script_path_for(subcommand: str) -> Path:
    rel = SUBCOMMAND_SCRIPTS[subcommand]
    return repo_root() / rel


def normalize_passthrough_args(argv: list[str]) -> list[str]:
    """Drop a leading ``--`` separator used between wrapper and script flags."""
    if argv and argv[0] == "--":
        return argv[1:]
    return list(argv)


def build_subcommand_argv(subcommand: str, passthrough: list[str] | None = None) -> list[str]:
    """Build argv for subprocess without executing."""
    script = script_path_for(subcommand)
    return [sys.executable, str(script), *normalize_passthrough_args(passthrough or [])]


def run_subcommand(subcommand: str, passthrough: list[str] | None = None) -> int:
    cmd = build_subcommand_argv(subcommand, passthrough)
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root()),
        check=False,
    )
    return int(proc.returncode)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="origenlab-email-pipeline",
        description="Operator CLI wrapper — delegates to existing scripts under scripts/.",
        epilog=(
            "Pass script-specific flags after ``--``. Example: "
            "python -m origenlab_email_pipeline.cli status -- --json"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name, script_rel in SUBCOMMAND_SCRIPTS.items():
        sub.add_parser(
            name,
            help=_SUBCOMMAND_HELP.get(name, script_rel),
            description=f"Run {script_rel}",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    # First token is the subcommand; remainder forwarded (optional leading ``--``).
    command = argv[0]
    if command not in SUBCOMMAND_SCRIPTS:
        parser.error(f"unknown command {command!r}")

    passthrough = normalize_passthrough_args(argv[1:])
    return run_subcommand(command, passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
