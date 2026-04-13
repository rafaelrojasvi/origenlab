"""Guardrail: critical operator scripts stay at documented paths (catch accidental moves)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/mart/build_business_mart.py",
        "scripts/commercial/build_commercial_intel_v1.py",
        "scripts/qa/publish_gate.py",
        "scripts/leads/run_leads_operational_stack.sh",
        "scripts/_bootstrap.py",
        # Lead-account: canonical implementations under scripts/leads/; thin wrappers at scripts/*.py
        "scripts/leads/build_lead_account_rollup.py",
        "scripts/leads/match_lead_accounts_to_existing_orgs.py",
        "scripts/leads/validate_lead_account_rollup.py",
        "scripts/leads/audit_lead_org_quality.py",
        "scripts/leads/mark_outreach_state.py",
        "scripts/leads/audit_emails_export_gate.py",
        "scripts/build_lead_account_rollup.py",
        "scripts/match_lead_accounts_to_existing_orgs.py",
        "scripts/validate_lead_account_rollup.py",
        "scripts/audit_lead_org_quality.py",
    ],
)
def test_critical_script_path_exists(rel: str) -> None:
    p = REPO / rel
    assert p.is_file(), f"missing operational script: {p}"
