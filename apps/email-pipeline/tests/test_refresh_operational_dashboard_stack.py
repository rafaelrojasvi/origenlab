"""CLI tests for refresh_operational_dashboard_stack wrapper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_refresh_stack_help() -> None:
    script = REPO / "scripts" / "ops" / "refresh_operational_dashboard_stack.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cp.returncode == 0
    assert "--run-gmail-inbox" in cp.stdout
    assert "--skip-postgres-sync" in cp.stdout


def test_refresh_stack_dry_run_prints_steps() -> None:
    script = REPO / "scripts" / "ops" / "refresh_operational_dashboard_stack.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cp.returncode == 0
    assert "build_business_mart" in cp.stdout or "build_business_mart" in cp.stderr
