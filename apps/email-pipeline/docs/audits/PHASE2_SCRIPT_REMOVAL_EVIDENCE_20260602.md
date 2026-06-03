# Phase 2 — script removal evidence

Status: generated reference (read-only audit)
Owner: email-pipeline-maintainers
Last reviewed: 2026-06-02

**Purpose:** Evidence for Phase 4–5 deprecation/removal. Phase **5A** removed dated post-send shell orchestrators; Phase **5B** removed root lead-account wrappers; Phase **5C** removed legacy buyer opportunity queue builder; Phase **5D** removed archive outreach audit wrapper; Phase **5K** removed 2026-06-01 manual outreach registry and dated QA scripts; Phase **5Q** removed legacy `flag_reported_non_delivery_from_contacto.py` (canonical `--include-reported-non-delivery`).

Regenerate: `uv run pytest tests/test_script_removal_evidence.py::test_generate_removal_evidence_report -q`

---

## Deprecated / wrapper removal candidates

| Path | SCRIPT_MAP | Test-locked | Doc refs | Test refs | Script refs | Replacement | Suggested phase |
|------|------------|-------------|----------|-----------|-------------|-------------|-----------------|

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

## Removed in Phase 5C (2026-06-02)

| Path | Replacement | Removed phase |
|------|-------------|---------------|
| `scripts/qa/build_buyer_opportunity_queue.py` | scripts/qa/build_equipment_first_opportunity_queue.py + scripts/qa/build_equipment_first_operator_queue.py | 5C |

## Removed in Phase 5D (2026-06-02)

| Path | Replacement | Removed phase |
|------|-------------|---------------|
| `scripts/leads/advanced/export_archive_outreach_candidates.py` | scripts/leads/build_archive_send_batch.py --audit-only | 5D |

## Removed in Phase 5K (2026-06-02)

| Path | Replacement | Removed phase |
|------|-------------|---------------|
| `src/origenlab_email_pipeline/campaigns/manual_outreach_2026_06_01.py` | scripts/qa/build_post_send_digest.py + docs/pipeline/POST_SEND_SAFE_LOOP.md | 5K |
| `scripts/qa/build_manual_outreach_2026_06_01_digest.py` | scripts/qa/build_post_send_digest.py | 5K |
| `scripts/qa/apply_manual_outreach_2026_06_01_corrections.py` | docs/pipeline/POST_SEND_SAFE_LOOP.md + generic suppression tools | 5K |

## Removed in Phase 5Q (2026-06-02)

| Path | Replacement | Removed phase |
|------|-------------|---------------|
| `scripts/tools/flag_reported_non_delivery_from_contacto.py` | scripts/tools/flag_ndr_bounces_from_contacto.py --include-reported-non-delivery + scripts/qa/build_ndr_review_queue.py | 5Q |

## Phase 3 refactor targets (keep entrypoints; lock behavior first)

| Path | Notes |
|------|-------|
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Extract IMAP helpers; tests in test_workspace_gmail_imap_ingest.py — future |
| `scripts/qa/export_contacted_lead_overlap_audit.py` | Golden CSV columns locked in test_export_contacted_lead_overlap_audit.py — library split done; entrypoint unchanged |
| `scripts/qa/export_email_conversation_intelligence.py` | Golden CSV columns locked in test_export_email_conversation_intelligence.py — library split done; entrypoint unchanged |

## Completed Phase 5P / Stage 6F1 (mart CLI)

| Path | Notes |
|------|-------|
| `scripts/mart/build_business_mart.py` | Done (Phase 5P / Stage 6F1): CLI orchestration → core/mart/build_business_mart_cli.py; operator script path + SAFETY banner unchanged; tests in test_build_business_mart.py, test_build_business_mart_phase2.py |

## Interpretation

- **Test-locked yes** → remove only after updating `test_critical_script_paths.py`, `test_lead_compatibility_wrappers.py`, or other contract tests in the same PR.
- **High doc refs** → update RUNBOOK/SCRIPT_MAP/AGENTS in Phase 1-style doc PR before deletion.
- **Wrappers** → Phase 4 deprecation stderr first; Phase 5 removal when root paths have zero external refs.
