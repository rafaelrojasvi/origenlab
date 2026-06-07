"""Tests for origenlab_email_pipeline.cli_modes."""

from __future__ import annotations

import argparse

import pytest

from origenlab_email_pipeline.cli_modes import (
    add_apply_dry_run_flags,
    add_audit_only_build_batch_flags,
    add_write_outputs_dry_run_flags,
    resolve_apply_dry_run_mode,
    resolve_audit_only_build_batch_mode,
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


def _audit_build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    add_audit_only_build_batch_flags(ap, build_help="Build full batch.")
    return ap


def test_add_audit_only_build_batch_flags_adds_both_flags() -> None:
    ap = _audit_build_parser()
    names = {a.dest for a in ap._actions if a.dest not in {"help"}}
    assert names == {"audit_only", "build_batch"}


def test_audit_build_default_resolves_to_audit_only() -> None:
    ap = _audit_build_parser()
    args = ap.parse_args([])
    mode = resolve_audit_only_build_batch_mode(ap, args)
    assert mode.audit_only is True
    assert mode.build_batch is False


def test_audit_only_flag_resolves_to_audit_only() -> None:
    ap = _audit_build_parser()
    args = ap.parse_args(["--audit-only"])
    mode = resolve_audit_only_build_batch_mode(ap, args)
    assert mode.audit_only is True
    assert mode.build_batch is False


def test_build_batch_flag_resolves_to_build_mode() -> None:
    ap = _audit_build_parser()
    args = ap.parse_args(["--build-batch"])
    mode = resolve_audit_only_build_batch_mode(ap, args)
    assert mode.audit_only is False
    assert mode.build_batch is True


def test_audit_only_and_build_batch_together_rejected() -> None:
    ap = _audit_build_parser()
    args = ap.parse_args(["--audit-only", "--build-batch"])
    with pytest.raises(SystemExit) as exc:
        resolve_audit_only_build_batch_mode(ap, args)
    assert exc.value.code == 2
