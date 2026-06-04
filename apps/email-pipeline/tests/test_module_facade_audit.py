"""Tests for read-only module facade audit script and operator CLI wiring."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.operator_cli.constants import SUBCOMMAND_SCRIPTS

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_SCRIPT = REPO / "scripts" / "qa" / "audit_module_facades.py"


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(_SRC)}


def _run_audit(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_audit_module_facades_json_exit_zero() -> None:
    proc = _run_audit("--json")
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["scanned_files"] > 0
    assert "summary" in report
    assert "pairs" in report
    assert isinstance(report["pairs"], list)


def test_business_mart_classified_root_impl_with_core_facade() -> None:
    proc = _run_audit("--json")
    report = json.loads(proc.stdout)
    match = next(p for p in report["pairs"] if p["basename"] == "business_mart.py")
    assert match["classification"] == "root_implementation_with_subpackage_facade"
    paths = {e["path"]: e for e in match["paths"]}
    assert paths["business_mart.py"]["is_root"] is True
    assert paths["business_mart.py"]["is_facade"] is False
    assert paths["core/mart/business_mart.py"]["is_facade"] is True


def test_schemas_classified_same_basename_distinct_domains() -> None:
    proc = _run_audit("--json")
    report = json.loads(proc.stdout)
    match = next(p for p in report["pairs"] if p["basename"] == "schemas.py")
    assert match["classification"] == "same_basename_distinct_domains"
    tops = {str(e["path"]).split("/")[0] for e in match["paths"]}
    assert tops >= {"tatiana_copilot", "postgres_dashboard_api"}


def test_fail_on_manual_review_default_zero_for_current_tree() -> None:
    proc = _run_audit("--fail-on-manual-review")
    assert proc.returncode == 0, proc.stderr


def test_operator_cli_maps_audit_facades() -> None:
    assert SUBCOMMAND_SCRIPTS["audit-facades"] == "scripts/qa/audit_module_facades.py"
    script = REPO / SUBCOMMAND_SCRIPTS["audit-facades"]
    assert script.is_file()


def test_audit_facades_in_operator_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "origenlab_email_pipeline.cli", "--help"],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "audit-facades" in proc.stdout
