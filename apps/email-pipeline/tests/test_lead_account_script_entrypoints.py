"""Smoke: canonical lead-account scripts start (``--help`` exit 0)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/leads/advanced/build_lead_account_rollup.py",
        "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py",
        "scripts/leads/advanced/validate_lead_account_rollup.py",
        "scripts/leads/advanced/audit_lead_org_quality.py",
    ],
)
def test_lead_account_script_help_exits_zero(rel: str) -> None:
    script = REPO / rel
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
