"""Generic subcommand subprocess runner."""

from __future__ import annotations

import subprocess
import sys

from origenlab_email_pipeline.operator_cli.constants import (
    HELP_ONLY_SUBCOMMANDS,
    MIRROR_DASHBOARD_COMMAND,
)
from origenlab_email_pipeline.operator_cli.gmail import (
    build_gmail_ingest_folders_argv,
    run_gmail_ingest,
)
from origenlab_email_pipeline.operator_cli.mirror import run_mirror_dashboard
from origenlab_email_pipeline.operator_cli.paths import (
    normalize_passthrough_args,
    repo_root,
    script_path_for,
)


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


def run_subcommand(
    subcommand: str,
    passthrough: list[str] | None = None,
    *,
    mirror_apply: bool = False,
    mirror_alembic: bool = False,
) -> int:
    if subcommand == "gmail-ingest":
        return run_gmail_ingest(passthrough)
    if subcommand == "gmail-ingest-folders":
        proc = subprocess.run(build_gmail_ingest_folders_argv(), cwd=str(repo_root()), check=False)
        return int(proc.returncode)
    if subcommand == MIRROR_DASHBOARD_COMMAND:
        return run_mirror_dashboard(apply=mirror_apply, alembic=mirror_alembic, passthrough=passthrough)
    cmd = build_subcommand_argv(subcommand, passthrough)
    proc = subprocess.run(cmd, cwd=str(repo_root()), check=False)
    return int(proc.returncode)
