# Reduction shortlist — email-pipeline (2026-06-07)

**Status:** read-only audit / planning doc (PR #120)  
**Date:** 2026-06-07  
**Scope:** `apps/email-pipeline` scripts and docs — **next few PRs only**  
**Authority for daily ops (unchanged):** [`SCRIPT_MAP.md`](../SCRIPT_MAP.md), [`RUNBOOK.md`](../RUNBOOK.md), [`OUTBOUND_SOURCE_OF_TRUTH.md`](../OUTBOUND_SOURCE_OF_TRUTH.md)

---

## Scope and safety rules

This document lists **evidence-backed reduction candidates** for small, safe follow-up PRs. It is **not** a deletion order.

**Rules for every candidate PR:**

1. **Docs/tests first** unless the change is a narrowly scoped CLI default (apply gate, audit-only default).
2. **Do not delete scripts** without import/reference checks, contract tests, and operator sign-off.
3. **Planners are not deletion authority** — `plan_function_surface.py` and `plan_import_surface.py` label risk and surface area; zero-import counts do **not** prove a file is unused.
4. **Prefer** `apply_gate`, `audit_only_default`, and `lab_boundary` over hard deletes.
5. **Do not run** `--apply`, send, purge, NDR apply, Postgres migrate/mirror apply, or daily-core apply during validation of these items.

**Evidence run (local, not committed):**

```bash
cd apps/email-pipeline
uv run python scripts/qa/plan_function_surface.py \
  --out-dir reports/local/reduction-shortlist-20260607/function-surface
uv run python scripts/qa/plan_import_surface.py \
  --out-dir reports/local/reduction-shortlist-20260607/import-surface
```

**Planner snapshot (2026-06-07):**

| Planner | Key counts |
|---------|------------|
| `plan_function_surface.py` | 283 src + 182 script files; 2697 functions; 35 scripts with `--apply` |
| `plan_import_surface.py` | 3352 import edges; 10 zero doc/test reference scripts; 15 dangerous paths flagged |
| Likely buckets (function surface) | `tatiana_lab` 40 files; `campaigns` 15; `postgres_mirror` 46; `lead_research` 62 |
| Risk buckets | `send_or_purge` 6; `outbound_apply` 7; `postgres_mirror_or_migration` 79 |

Outputs live under `reports/local/reduction-shortlist-20260607/` — **do not commit** those CSVs.

---

## What was already reduced (recent PRs)

| PR | Change | Effect |
|----|--------|--------|
| **#117** | Stale reduction references cleanup | Removed live-operator mentions of deleted paths (e.g. `build_buyer_opportunity_queue.py`); guarded by `test_stale_reduction_references.py` |
| **#118** | `prepare_active_workspace.py` apply gate | Legacy hunt workspace prep is **plan-only by default**; `--apply` required to move/write under `reports/out/active/` |
| **#119** | `build_archive_send_batch.py` audit-only default | Alternate archive lane writes audit CSV/JSON by default; **`--build-batch`** required for send_ready/review CSVs; `--write-postgres-audit` requires `--build-batch` |

These are **done** — do not re-open unless regressions are found.

---

## No-touch / high-blast-radius paths

Do **not** treat these as reduction targets without explicit operator approval and a dedicated safety review.

| Path / module | Why |
|---------------|-----|
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | Canonical Gmail Sent ingest; Sent-history blocking truth |
| `scripts/qa/export_do_not_repeat_master.py` | Volume-lane DNR export |
| `scripts/qa/refresh_outbound_safety_memory.py` | Anti-repeat refresh chain |
| `scripts/tools/flag_ndr_bounces_from_contacto.py` | NDR scan; suppression with `--apply` |
| `scripts/qa/send_inline_html_email_via_gmail_api.py` | Break-glass send |
| `scripts/tools/purge_*_from_sqlite.py` | Cross-table DELETE |
| `scripts/sync/sync_*_postgres_mirror.py` | Postgres mirror load |
| `scripts/migrate/sqlite_*_to_postgres.py` | Postgres TRUNCATE/DELETE risk |
| `candidate_export_gate.py` / `outbound_core.py` / `outreach_contact_state.py` / `csv_contracts.py` | Shared outbound policy and sidecar |
| `origenlab daily-core` / `refresh-dashboard` runtime | Daily operator stack |
| `scripts/leads/export_next_marketing_recipients.py` | Lead lane canonical export |
| `scripts/leads/mark_sent_batch_contacted.py` | Post-send sidecar |
| `scripts/leads/import_lead_contact_research_csv.py` | Precision-lane DB writes |

**Already safe defaults (no further gate needed unless behavior drifts):**

- `scripts/tools/archive_reports_out_generated.py` — dry-run default; `--apply` moves files (no deletes)
- `scripts/qa/plan_reports_out_cleanup.py` — read-only planner
- `origenlab refresh-dashboard` / `daily-core` — plan-only default at CLI layer

---

## Current candidates

Action types used below: `docs_only_cleanup` · `apply_gate` · `audit_only_default` · `lab_boundary` · `move_later` · `delete_later_after_wrapper` · `no_action` · `needs_owner_review`

| Path | Current category | Why it is a candidate | Evidence | Proposed next action | Risk | PR type |
|------|------------------|----------------------|----------|----------------------|------|---------|
| `scripts/leads/advanced/export_marketing_from_contact_master.py` | parked_legacy / ARCHIVE_LANE exploratory | Writes marketing CSV + optional pilot CSV **by default**; overlaps archive mental model; not daily lane | SCRIPT_MAP ARCHIVE_LANE; 21 total refs (import planner); docstring says exploratory | **audit_only_default** or explicit `--export` flag (mirror #119 pattern) | medium | behavior + tests |
| `scripts/leads/campaigns/apply_ready8_contact_patch.py` | parked_legacy / niche campaign | Mutates `reports/out/active/*.csv` and `docs/generated/` **without** `--apply` | EXPERIMENTAL_PARKED; 2 doc refs; writes on every run | **apply_gate** (plan-only default) | medium | behavior + tests |
| `scripts/leads/campaigns/reconcile_deepresearch_50_with_current_cohort.py` | parked_legacy | DR50 niche reconciliation; not equipment-first policy | EXPERIMENTAL_PARKED; 4 total refs | **lab_boundary** doc cross-link only; optional **apply_gate** if it writes | low | docs_only_cleanup |
| `scripts/tatiana/*` (9 entrypoints) | parked_legacy | Tatiana drafting/eval; not volume or precision daily lanes | TATIANA_LAB_BOUNDARY; SCRIPT_MAP parked row; `tatiana_lab` bucket 40 files | **lab_boundary** — strengthen banners in RUNBOOK/SCRIPT_MAP; no moves in next PR | low | docs_only_cleanup |
| `scripts/dataset/*` (4 scripts) | parked_legacy | Cohort exports for Tatiana eval | EXPERIMENTAL_PARKED; e.g. `export_tatiana_candidate_cohort.py` 20 refs | **lab_boundary** | low | docs_only_cleanup |
| `scripts/ml/*` (`explore_email_clusters.py`, `email_ml_explore.py`) | parked_legacy | ML exploration; optional `--embeddings` in report batch | TATIANA_LAB_BOUNDARY; 2 scripts | **lab_boundary** | low | docs_only_cleanup |
| `scripts/reports/build_ml_report.py` | read_only_qa_report (lab) | ML/Tatiana report path; not daily ops | SCRIPT_MAP notes “Lab path”; tied to `--embeddings` | **lab_boundary** | low | docs_only_cleanup |
| `scripts/reports/run_all_reports.py` | read_only_qa_report | Orchestrator writes timestamped folder under `reports/out/` on every run | 4 total refs; subprocess driver | **apply_gate** or require explicit `--out` confirmation — **needs_owner_review** before changing default | medium | needs_owner_review |
| `scripts/qa/export_all_known_marketing_contacts.py` | active_operator_command (overlap) | Alternate merge of marketing CSVs; overlaps DNR chain partially | RUNBOOK “not daily”; 7 refs; writes `reports/out/active/` by default | **docs_only_cleanup** — clarify vs `export-dnr` / volume lane; optional dry-run flag later | low | docs_only_cleanup |
| `scripts/leads/precheck_archive_shortlist_commercial.py` | ARCHIVE_LANE helper | Standalone precheck after manual shortlist; already read-only | Docstring: no SQLite writes; 8 refs | **no_action** (already safe); optional doc link from archive RUNBOOK | low | docs_only_cleanup |
| `scripts/leads/advanced/run_contact_hunt_web_server.py` | parked_legacy / advanced | Local web server for hunt workflows | **0** doc/test refs (import planner) | **needs_owner_review** — confirm unused before any gate or archive | low | docs_only_cleanup |
| `scripts/leads/advanced/export_leads_spanish_csvs.py` | parked_legacy / advanced | Spanish CSV export helper | **0** total refs (import planner) | **delete_later_after_wrapper** — only after owner confirms + import scan | low | move_later |
| `scripts/leads/advanced/compare_archive_vs_lead_outreach.py` | parked_legacy / advanced | Compare archive vs lead lane outputs | 4 python imports; 0 doc refs | **move_later** — keep; document as audit helper | low | docs_only_cleanup |
| `scripts/leads/build_lead_research_sqlite.py` | unknown | Builds research SQLite artifact | 2 python imports; 0 doc refs | **needs_owner_review** | low | docs_only_cleanup |
| `scripts/leads/advanced/prepare_active_workspace.py` | parked_legacy | Legacy hunt workspace cleanup | **#118 done** — plan-only + `--apply` | **no_action** | — | — |
| `scripts/leads/build_archive_send_batch.py` | active_operator_command (alternate) | Archive batch lane | **#119 done** — audit-only default + `--build-batch` | **no_action** | — | — |
| `scripts/qa/build_buyer_opportunity_queue.py` | *(removed Phase 5C)* | Legacy tender queue | File absent; `test_stale_reduction_references.py` guards | **no_action** — **not a live target** | — | — |
| `src/origenlab_email_pipeline/core/research_automation.py` | research_lab (1683 LOC) | Largest src module; deep-research automation | function-surface top file; `research_lab` bucket | **move_later** — characterize splits; no delete | medium | docs_only_cleanup |
| Postgres mirror / migrate tree | parked / break-glass | Optional reporting mirror | 79 files in `postgres_mirror_or_migration` risk bucket | **no_action** — frozen per EXPERIMENTAL_PARKED | high | — |

---

## Suggested PR sequence (next 3–5)

1. **Lab boundary doc pass** — Tatiana / dataset / ml / campaigns / `build_ml_report.py` (`lab_boundary`, docs + tests only).
2. **`export_marketing_from_contact_master.py` safe default** — audit-only or explicit export flag (`audit_only_default`, small behavior change + tests).
3. **`apply_ready8_contact_patch.py` apply gate** — plan-only default (`apply_gate`, mirror #118).
4. **Zero-ref advanced scripts owner review** — `export_leads_spanish_csvs.py`, `run_contact_hunt_web_server.py` (`needs_owner_review` → then wrapper or delete_later).
5. **`export_all_known_marketing_contacts.py` doc clarification** — vs DNR/volume lane (`docs_only_cleanup`).

---

## Related docs and tests

- [`SCRIPT_MAP.md`](../SCRIPT_MAP.md) — canonical classification
- [`EXPERIMENTAL_PARKED.md`](../EXPERIMENTAL_PARKED.md) — Postgres / Tatiana / campaigns index
- [`TATIANA_LAB_BOUNDARY.md`](../TATIANA_LAB_BOUNDARY.md) — lab vs daily outbound
- [`CODEBASE_SIMPLIFICATION_AUDIT_20260602.md`](CODEBASE_SIMPLIFICATION_AUDIT_20260602.md) — broader audit (some counts stale)
- [`test_stale_reduction_references.py`](../../tests/test_stale_reduction_references.py) — guards removed targets
- [`test_reduction_shortlist_docs.py`](../../tests/test_reduction_shortlist_docs.py) — locks this shortlist

**Reminder:** Planners write to `reports/local/` only. Re-run planners before each reduction wave; do not treat CSV output as committed truth.
