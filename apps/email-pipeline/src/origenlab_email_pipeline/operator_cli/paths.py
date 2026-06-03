"""Repo root and script path helpers for operator CLI."""

from __future__ import annotations

from pathlib import Path

from origenlab_email_pipeline.operator_cli.constants import (
    GMAIL_INGEST_SCRIPT,
    MIRROR_DASHBOARD_SYNC_SCRIPT,
    SUBCOMMAND_SCRIPTS,
)


def repo_root() -> Path:
    """apps/email-pipeline directory (parent of ``src/``)."""
    return Path(__file__).resolve().parents[3]


def gmail_ingest_script_path() -> Path:
    return repo_root() / GMAIL_INGEST_SCRIPT


def mirror_dashboard_sync_script_path() -> Path:
    return repo_root() / MIRROR_DASHBOARD_SYNC_SCRIPT


def script_path_for(subcommand: str) -> Path:
    rel = SUBCOMMAND_SCRIPTS[subcommand]
    return repo_root() / rel


def normalize_passthrough_args(argv: list[str]) -> list[str]:
    """Drop a leading ``--`` separator used between wrapper and script flags."""
    if argv and argv[0] == "--":
        return argv[1:]
    return list(argv)
