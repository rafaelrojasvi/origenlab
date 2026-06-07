"""Tests for origenlab_email_pipeline.cli_modes."""

from __future__ import annotations

import argparse

import pytest

from origenlab_email_pipeline.cli_modes import (
    add_apply_dry_run_flags,
    add_write_outputs_dry_run_flags,
    resolve_apply_dry_run_mode,
    resolve_write_outputs_dry_run_mode,
)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    add_apply_dry_run_flags(ap, apply_help="Apply changes.")
    return ap


def test_add_apply_dry_run_flags_adds_both_flags() -> None:
    ap = _parser()
    names = {a.dest for a in ap._actions if a.dest not in {"help"}}
    assert names == {"apply", "dry_run"}


def test_default_resolves_to_plan_only() -> None:
    ap = _parser()
    args = ap.parse_args([])
    mode = resolve_apply_dry_run_mode(ap, args)
    assert mode.apply is False
    assert mode.dry_run is True


def test_apply_flag_resolves_to_apply_mode() -> None:
    ap = _parser()
    args = ap.parse_args(["--apply"])
    mode = resolve_apply_dry_run_mode(ap, args)
    assert mode.apply is True
    assert mode.dry_run is False


def test_dry_run_flag_resolves_to_plan_only() -> None:
    ap = _parser()
    args = ap.parse_args(["--dry-run"])
    mode = resolve_apply_dry_run_mode(ap, args)
    assert mode.apply is False
    assert mode.dry_run is True


def test_apply_and_dry_run_together_rejected() -> None:
    ap = _parser()
    args = ap.parse_args(["--apply", "--dry-run"])
    with pytest.raises(SystemExit) as exc:
        resolve_apply_dry_run_mode(ap, args)
    assert exc.value.code == 2


def _write_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    add_write_outputs_dry_run_flags(ap, write_help="Write outputs.")
    return ap


def test_add_write_outputs_dry_run_flags_adds_both_flags() -> None:
    ap = _write_parser()
    names = {a.dest for a in ap._actions if a.dest not in {"help"}}
    assert names == {"write_outputs", "dry_run"}


def test_write_outputs_default_resolves_to_plan_only() -> None:
    ap = _write_parser()
    args = ap.parse_args([])
    mode = resolve_write_outputs_dry_run_mode(ap, args)
    assert mode.write_outputs is False
    assert mode.dry_run is True


def test_write_outputs_flag_resolves_to_write_mode() -> None:
    ap = _write_parser()
    args = ap.parse_args(["--write-outputs"])
    mode = resolve_write_outputs_dry_run_mode(ap, args)
    assert mode.write_outputs is True
    assert mode.dry_run is False


def test_write_outputs_dry_run_flag_resolves_to_plan_only() -> None:
    ap = _write_parser()
    args = ap.parse_args(["--dry-run"])
    mode = resolve_write_outputs_dry_run_mode(ap, args)
    assert mode.write_outputs is False
    assert mode.dry_run is True


def test_write_outputs_and_dry_run_together_rejected() -> None:
    ap = _write_parser()
    args = ap.parse_args(["--write-outputs", "--dry-run"])
    with pytest.raises(SystemExit) as exc:
        resolve_write_outputs_dry_run_mode(ap, args)
    assert exc.value.code == 2
