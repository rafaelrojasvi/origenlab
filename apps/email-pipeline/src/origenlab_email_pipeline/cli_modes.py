from __future__ import annotations

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass


@dataclass(frozen=True)
class ApplyDryRunMode:
    apply: bool
    dry_run: bool


def add_apply_dry_run_flags(
    parser: ArgumentParser,
    *,
    apply_help: str,
    dry_run_help: str = "Plan only (same as default; kept for compatibility).",
) -> None:
    parser.add_argument("--apply", action="store_true", help=apply_help)
    parser.add_argument("--dry-run", action="store_true", help=dry_run_help)


def resolve_apply_dry_run_mode(
    parser: ArgumentParser,
    args: Namespace,
    *,
    conflict_message: str = "--apply and --dry-run cannot be used together",
) -> ApplyDryRunMode:
    if bool(getattr(args, "apply", False)) and bool(getattr(args, "dry_run", False)):
        parser.error(conflict_message)
    apply = bool(getattr(args, "apply", False))
    return ApplyDryRunMode(apply=apply, dry_run=not apply)


@dataclass(frozen=True)
class WriteOutputsDryRunMode:
    write_outputs: bool
    dry_run: bool


def add_write_outputs_dry_run_flags(
    parser: ArgumentParser,
    *,
    write_help: str,
    dry_run_help: str = "Plan only (same as default; kept for compatibility).",
) -> None:
    parser.add_argument("--write-outputs", action="store_true", help=write_help)
    parser.add_argument("--dry-run", action="store_true", help=dry_run_help)


def resolve_write_outputs_dry_run_mode(
    parser: ArgumentParser,
    args: Namespace,
    *,
    conflict_message: str = "--write-outputs and --dry-run cannot be used together",
) -> WriteOutputsDryRunMode:
    if bool(getattr(args, "write_outputs", False)) and bool(getattr(args, "dry_run", False)):
        parser.error(conflict_message)
    write_outputs = bool(getattr(args, "write_outputs", False))
    return WriteOutputsDryRunMode(write_outputs=write_outputs, dry_run=not write_outputs)
