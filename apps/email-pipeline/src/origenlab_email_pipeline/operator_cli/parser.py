"""Argparse setup and main dispatch for operator CLI."""

from __future__ import annotations

import argparse
import sys

from origenlab_email_pipeline.operator_cli.constants import (
    CLI_COMMAND_NAMES,
    DAILY_CORE_COMMAND,
    GMAIL_INGEST_SCRIPT,
    HELP_ONLY_SUBCOMMANDS,
    MIRROR_DASHBOARD_COMMAND,
    REFRESH_DASHBOARD_COMMAND,
    SPECIAL_COMMANDS,
    SUBCOMMAND_HELP,
    SUBCOMMAND_SCRIPTS,
)
from origenlab_email_pipeline.operator_cli.gmail import (
    print_gmail_ingest_folders_help,
    print_gmail_ingest_help_help,
    validate_gmail_ingest_passthrough,
)
from origenlab_email_pipeline.operator_cli.mirror import (
    parse_mirror_dashboard_wrapper_args,
    print_mirror_dashboard_help,
)
from origenlab_email_pipeline.operator_cli.paths import normalize_passthrough_args
from origenlab_email_pipeline.operator_cli.refresh import (
    parse_daily_core_wrapper_args,
    parse_refresh_dashboard_wrapper_args,
    print_daily_core_help,
    print_refresh_dashboard_help,
    run_daily_core,
    run_refresh_dashboard,
)
from origenlab_email_pipeline.operator_cli.runner import run_subcommand


def _add_refresh_wrapper_flags(
    parser: argparse.ArgumentParser,
    *,
    include_mirror_dry_run: bool,
    no_mirror_help: str = "With --apply: skip Postgres mirror step",
) -> None:
    parser.add_argument("--apply", action="store_true", help="Run workflow steps (stop on first failure)")
    parser.add_argument("--no-mirror", action="store_true", help=no_mirror_help)
    if include_mirror_dry_run:
        parser.add_argument(
            "--mirror-dry-run",
            action="store_true",
            help="With --apply: end with mirror-dashboard dry-run (not --apply)",
        )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="With --apply: skip gmail-ingest (use when already ingested)",
    )
    parser.add_argument(
        "--since-days",
        metavar="N",
        type=int,
        help="With --apply: pass --since-days N to gmail-ingest only",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="origenlab-email-pipeline",
        description="Operator CLI wrapper — delegates to existing scripts under scripts/.",
        epilog=(
            "Pass script-specific flags after ``--``. Example: "
            "origenlab status -- --json. "
            "gmail-ingest: safe INBOX + Sent ingest (--replace-source rejected). "
            "gmail-ingest-help: ingest --help only. "
            "mirror-dashboard: Postgres mirror sync (dry-run default; requires Postgres URL env). "
            "refresh-dashboard: orchestrated stack refresh (plan-only default). "
            "daily-core: daily operating alias (plan-only default; --apply uses feature-backed mart rebuild)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name in CLI_COMMAND_NAMES:
        script_rel = SUBCOMMAND_SCRIPTS.get(name, GMAIL_INGEST_SCRIPT)
        if name in (REFRESH_DASHBOARD_COMMAND, DAILY_CORE_COMMAND):
            p = sub.add_parser(name, help=SUBCOMMAND_HELP[name], description=SUBCOMMAND_HELP[name])
            _add_refresh_wrapper_flags(
                p,
                include_mirror_dry_run=(name == REFRESH_DASHBOARD_COMMAND),
                no_mirror_help=(
                    "Accepted for compatibility; daily-core never runs mirror"
                    if name == DAILY_CORE_COMMAND
                    else "With --apply: skip Postgres mirror step"
                ),
            )
            if name == DAILY_CORE_COMMAND:
                p.add_argument(
                    "--mirror-dry-run",
                    action="store_true",
                    help=argparse.SUPPRESS,
                )
            continue
        if name == MIRROR_DASHBOARD_COMMAND:
            p = sub.add_parser(
                name,
                help=SUBCOMMAND_HELP[name],
                description=SUBCOMMAND_HELP[name],
            )
            p.add_argument(
                "--apply",
                action="store_true",
                help="Run sync without --dry-run (writes Postgres mirror)",
            )
            p.add_argument(
                "--alembic",
                action="store_true",
                help="With --apply: run alembic upgrade head before sync",
            )
            p.add_argument(
                "--live",
                action="store_true",
                help=(
                    "Include live dashboard optional loaders (warm cases, equipment "
                    "opportunities, commercial deals); dry-run unless --apply"
                ),
            )
            p.add_argument(
                "--operator",
                metavar="VALUE",
                help="With --live --apply: operator id for optional loader audit (alias: --updated-by)",
            )
            p.add_argument(
                "--updated-by",
                metavar="VALUE",
                help="With --live --apply: operator id for optional loader audit",
            )
            p.add_argument(
                "--reason",
                metavar="VALUE",
                help="With --live --apply: audit reason for optional loader writes",
            )
            continue
        sub.add_parser(
            name,
            help=SUBCOMMAND_HELP.get(name, script_rel),
            description=f"Run {script_rel}" if name in SUBCOMMAND_SCRIPTS else SUBCOMMAND_HELP.get(name, ""),
        )
    return parser


def _is_known_command(command: str) -> bool:
    return command in SUBCOMMAND_SCRIPTS or command in SPECIAL_COMMANDS


def _wrapper_help_requested(argv_tail: list[str]) -> bool:
    return len(argv_tail) == 1 and argv_tail[0] in ("-h", "--help")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    command = argv[0]
    if not _is_known_command(command):
        parser.error(f"unknown command {command!r}")

    if command == REFRESH_DASHBOARD_COMMAND:
        if _wrapper_help_requested(argv[1:]):
            print_refresh_dashboard_help()
            return 0
        try:
            refresh_opts = parse_refresh_dashboard_wrapper_args(argv[1:])
        except ValueError as exc:
            parser.error(str(exc))
        return run_refresh_dashboard(refresh_opts)

    if command == DAILY_CORE_COMMAND:
        if _wrapper_help_requested(argv[1:]):
            print_daily_core_help()
            return 0
        try:
            daily_opts = parse_daily_core_wrapper_args(argv[1:])
        except ValueError as exc:
            parser.error(str(exc))
        return run_daily_core(daily_opts)

    mirror_apply = False
    mirror_alembic = False
    passthrough: list[str]
    if command == MIRROR_DASHBOARD_COMMAND:
        if _wrapper_help_requested(argv[1:]):
            print_mirror_dashboard_help()
            return 0
        try:
            mirror_apply, mirror_alembic, passthrough = parse_mirror_dashboard_wrapper_args(argv[1:])
        except ValueError as exc:
            parser.error(str(exc))
    elif command == "gmail-ingest-folders" and _wrapper_help_requested(argv[1:]):
        print_gmail_ingest_folders_help()
        return 0
    elif command == "gmail-ingest-help" and _wrapper_help_requested(argv[1:]):
        print_gmail_ingest_help_help()
        return 0
    else:
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

    return run_subcommand(
        command,
        passthrough,
        mirror_apply=mirror_apply,
        mirror_alembic=mirror_alembic,
    )
