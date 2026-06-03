"""Gmail ingest CLI builders and runners."""

from __future__ import annotations

import subprocess
import sys

from origenlab_email_pipeline.operator_cli.constants import (
    GMAIL_INGEST_INBOX_FOLDER,
    GMAIL_INGEST_SCRIPT,
    GMAIL_INGEST_SENT_FOLDER,
)
from origenlab_email_pipeline.operator_cli.paths import (
    gmail_ingest_script_path,
    normalize_passthrough_args,
    repo_root,
)


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


def run_gmail_ingest(passthrough: list[str] | None = None) -> int:
    """Run INBOX then Sent ingest; stop on first non-zero exit."""
    cwd = str(repo_root())
    for cmd in build_gmail_ingest_argv_list(passthrough):
        proc = subprocess.run(cmd, cwd=cwd, check=False)
        if proc.returncode != 0:
            return int(proc.returncode)
    return 0


def print_gmail_ingest_folders_help() -> None:
    print(
        "gmail-ingest-folders — list Gmail IMAP folder labels\n\n"
        "  uv run origenlab gmail-ingest-folders\n\n"
        f"Runs {GMAIL_INGEST_SCRIPT} --list-folders (contacts Gmail).\n"
        "Use when [Gmail]/Enviados differs; then run gmail-ingest or the ingest script directly.\n"
    )


def print_gmail_ingest_help_help() -> None:
    print(
        "gmail-ingest-help — show ingest script --help\n\n"
        "  uv run origenlab gmail-ingest-help\n\n"
        f"Runs {GMAIL_INGEST_SCRIPT} --help (no Gmail connection).\n"
        "For daily ingest use: uv run origenlab gmail-ingest\n"
    )
