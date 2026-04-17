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
        "scripts/qa/check_outbound_readiness.py",
        "scripts/qa/print_outbound_run_summary.py",
        "scripts/leads/run_leads_operational_stack.sh",
        "scripts/_bootstrap.py",
        # Canonical outbound + commercial precheck (operator surface)
        "scripts/leads/build_archive_send_batch.py",
        "scripts/leads/export_next_marketing_recipients.py",
        "scripts/leads/precheck_archive_shortlist_commercial.py",
        "scripts/leads/add_manual_contact_suppressions.py",
        "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py",
        # Demoted paths: implementations + folder READMEs (layout contract)
        "scripts/leads/advanced/export_archive_outreach_candidates.py",
        "scripts/leads/advanced/README.md",
        "scripts/leads/campaigns/README.md",
        # Lead-account: implementations under scripts/leads/advanced/; thin wrappers at scripts/*.py
        "scripts/leads/advanced/build_lead_account_rollup.py",
        "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py",
        "scripts/leads/advanced/validate_lead_account_rollup.py",
        "scripts/leads/advanced/audit_lead_org_quality.py",
        "scripts/leads/mark_outreach_state.py",
        "scripts/leads/import_operator_outreach_blocklist.py",
        "scripts/leads/build_manual_html_outreach_batch.py",
        "scripts/leads/advanced/audit_emails_export_gate.py",
        "scripts/build_lead_account_rollup.py",
        "scripts/match_lead_accounts_to_existing_orgs.py",
        "scripts/validate_lead_account_rollup.py",
        "scripts/audit_lead_org_quality.py",
    ],
)
def test_critical_script_path_exists(rel: str) -> None:
    p = REPO / rel
    assert p.is_file(), f"missing operational script: {p}"
