# Phase 2 — script removal evidence

Status: generated reference (read-only audit)
Owner: email-pipeline-maintainers
Last reviewed: 2026-06-02

**Purpose:** Evidence for Phase 4–5 deprecation/removal. Phase **5A** removed dated post-send shell orchestrators; Phase **5B** removed root lead-account compatibility wrappers.

Regenerate: `uv run pytest tests/test_script_removal_evidence.py::test_generate_removal_evidence_report -q`

---

## Deprecated / wrapper removal candidates

| Path | SCRIPT_MAP | Test-locked | Doc refs | Test refs | Script refs | Replacement | Suggested phase |
|------|------------|-------------|----------|-----------|-------------|-------------|-----------------|
| `scripts/qa/build_buyer_opportunity_queue.py` | yes | yes | 4 | 6 | 1 | build_equipment_first_opportunity_queue.py + build_equipment_first_operator_queue.py | 5 |
| `scripts/tools/flag_reported_non_delivery_from_contacto.py` | yes | no | 4 | 4 | 1 | flag_ndr_bounces_from_contacto.py (NDR) + human review queue | 5 |
| `scripts/leads/advanced/export_archive_outreach_candidates.py` | yes | yes | 5 | 5 | 1 | build_archive_send_batch.py --audit-only | 5 |

## Removed in Phase 5A (2026-06-02)

| Path | Replacement | Removed phase |
|------|-------------|---------------|
| `scripts/ops/run_post_send_2026_06_01_refresh.sh` | docs/pipeline/POST_SEND_SAFE_LOOP.md step-by-step loop | 5A |
| `scripts/ops/run_manual_outreach_2026_06_01_post_send_refresh.sh` | docs/pipeline/POST_SEND_SAFE_LOOP.md step-by-step loop | 5A |

## Removed in Phase 5B (2026-06-02)

| Path | Replacement | Removed phase |
|------|-------------|---------------|
| `scripts/build_lead_account_rollup.py` | scripts/leads/advanced/build_lead_account_rollup.py | 5B |
| `scripts/match_lead_accounts_to_existing_orgs.py` | scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py | 5B |
| `scripts/validate_lead_account_rollup.py` | scripts/leads/advanced/validate_lead_account_rollup.py | 5B |
| `scripts/audit_lead_org_quality.py` | scripts/leads/advanced/audit_lead_org_quality.py | 5B |

## Phase 3 refactor targets (keep entrypoints; lock behavior first)

| Path | Notes |
|------|-------|
| `scripts/mart/build_business_mart.py` | Split main() → src; tests in test_build_business_mart.py |
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Extract IMAP helpers; tests in test_workspace_gmail_imap_ingest.py |
| `scripts/qa/export_contacted_lead_overlap_audit.py` | Golden CSV columns locked in test_export_contacted_lead_overlap_audit.py |
| `scripts/qa/export_email_conversation_intelligence.py` | Golden CSV columns locked in test_export_email_conversation_intelligence.py |

## Interpretation

- **Test-locked yes** → remove only after updating `test_critical_script_paths.py`, `test_lead_compatibility_wrappers.py`, or other contract tests in the same PR.
- **High doc refs** → update RUNBOOK/SCRIPT_MAP/AGENTS in Phase 1-style doc PR before deletion.
- **Wrappers** → Phase 4 deprecation stderr first; Phase 5 removal when root paths have zero external refs.
