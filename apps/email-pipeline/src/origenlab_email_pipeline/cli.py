"""Unified operator CLI — thin entrypoint (Phase 8B).

Delegates to ``operator_cli`` package. Does not change script behavior.
"""

from __future__ import annotations

from origenlab_email_pipeline.operator_cli import (
    CLI_COMMAND_NAMES,
    GMAIL_INGEST_INBOX_FOLDER,
    GMAIL_INGEST_SENT_FOLDER,
    HELP_ONLY_SUBCOMMANDS,
    MIRROR_DASHBOARD_SYNC_SCRIPT,
    POSTGRES_ENV_VARS,
    REFRESH_DASHBOARD_USAGE,
    RefreshDashboardOptions,
    SUBCOMMAND_SCRIPTS,
    build_gmail_ingest_argv_list,
    build_mirror_dashboard_argv_list,
    build_mirror_dashboard_sync_argv,
    build_refresh_dashboard_steps,
    build_subcommand_argv,
    missing_postgres_env_message,
    mirror_dashboard_uses_cloud_postgres_only,
    normalize_passthrough_args,
    postgres_url_configured,
    repo_root,
    run_gmail_ingest,
    run_mirror_dashboard,
    run_refresh_dashboard,
    run_subcommand,
    script_path_for,
    validate_gmail_ingest_passthrough,
)
from origenlab_email_pipeline.operator_cli.parser import main

__all__ = [
    "CLI_COMMAND_NAMES",
    "GMAIL_INGEST_INBOX_FOLDER",
    "GMAIL_INGEST_SENT_FOLDER",
    "HELP_ONLY_SUBCOMMANDS",
    "MIRROR_DASHBOARD_SYNC_SCRIPT",
    "POSTGRES_ENV_VARS",
    "REFRESH_DASHBOARD_USAGE",
    "RefreshDashboardOptions",
    "SUBCOMMAND_SCRIPTS",
    "build_gmail_ingest_argv_list",
    "build_mirror_dashboard_argv_list",
    "build_mirror_dashboard_sync_argv",
    "build_refresh_dashboard_steps",
    "build_subcommand_argv",
    "main",
    "missing_postgres_env_message",
    "mirror_dashboard_uses_cloud_postgres_only",
    "normalize_passthrough_args",
    "postgres_url_configured",
    "repo_root",
    "run_gmail_ingest",
    "run_mirror_dashboard",
    "run_refresh_dashboard",
    "run_subcommand",
    "script_path_for",
    "validate_gmail_ingest_passthrough",
]

if __name__ == "__main__":
    raise SystemExit(main())
