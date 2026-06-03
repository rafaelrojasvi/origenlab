"""Tests for unified operator CLI wrapper (Phase 6B) — no heavy script execution."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.cli import (
    SUBCOMMAND_SCRIPTS,
    build_subcommand_argv,
    normalize_passthrough_args,
    repo_root,
    script_path_for,
)

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(_SRC)}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "origenlab_email_pipeline.cli", *args],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_cli_help_exits_zero() -> None:
    cp = _run_cli("--help")
    assert cp.returncode == 0, cp.stderr
    assert "origenlab-email-pipeline" in cp.stdout or "Operator CLI" in cp.stdout


@pytest.mark.parametrize("name", list(SUBCOMMAND_SCRIPTS))
def test_subcommand_appears_in_help(name: str) -> None:
    cp = _run_cli("--help")
    assert cp.returncode == 0
    assert name in cp.stdout


@pytest.mark.parametrize("name,rel", SUBCOMMAND_SCRIPTS.items())
def test_script_path_mapping_exists(name: str, rel: str) -> None:
    path = script_path_for(name)
    assert path == repo_root() / rel
    assert path.is_file(), f"missing script for {name}: {path}"


def test_build_subcommand_argv_no_passthrough() -> None:
    argv = build_subcommand_argv("status")
    assert argv[0] == sys.executable
    assert argv[1].endswith("scripts/qa/operator_status.py")
    assert len(argv) == 2


def test_build_subcommand_argv_with_double_dash_passthrough() -> None:
    argv = build_subcommand_argv("status", ["--", "--json"])
    assert argv[-1] == "--json"
    assert "--" not in argv[2:]


def test_build_subcommand_argv_strict_validate() -> None:
    argv = build_subcommand_argv("validate-csvs", ["--strict"])
    assert argv[-1] == "--strict"
    assert "validate_campaign_csvs.py" in argv[1]


def test_normalize_passthrough_strips_leading_separator() -> None:
    assert normalize_passthrough_args(["--", "--json", "--verbose"]) == ["--json", "--verbose"]
    assert normalize_passthrough_args(["--json"]) == ["--json"]


def test_run_subcommand_not_invoked_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrapper tests must not spawn heavy QA scripts."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.cli.subprocess.run", fake_run)
    from origenlab_email_pipeline.cli import run_subcommand

    assert run_subcommand("check-readiness", ["--help"]) == 0
    assert len(calls) == 1
    assert calls[0][-1] == "--help"
    assert calls[0][1].endswith("check_outbound_readiness.py")
