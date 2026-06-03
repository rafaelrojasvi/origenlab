# Phase 8A — post-7C tree cleanup audit (read-only)

Status: audit (planning only)  
Owner: email-pipeline-maintainers  
Date: 2026-06-03  
Branch context: after Phase **7C** (`refresh-dashboard` workflow) merged to operator CLI

**Purpose:** Fresh inventory of the full `apps/email-pipeline` Python tree after Phases 6–7. **No moves, deletes, refactors, or mutating runs** in this audit.

**Planner artifacts (local, gitignored under `reports/out/`):**

- `reports/out/active/current/plan_script_consolidation_after_phase7c.json`
- `reports/out/active/current/plan_source_quality_after_phase7c.json`

Reproduce:

```bash
cd apps/email-pipeline
uv run python scripts/qa/plan_script_consolidation.py \
  --json-out reports/out/active/current/plan_script_consolidation_after_phase7c.json
uv run python scripts/qa/plan_source_quality.py \
  --json-out reports/out/active/current/plan_source_quality_after_phase7c.json \
  --top 100
```

---

## 1. Current counts

| Measure | Count | Notes |
|---------|------:|-------|
| **`scripts/**/*.py`** | **179** | Unchanged since Phase 6 checkpoint |
| **`src/**/*.py`** | **276** | Under `src/origenlab_email_pipeline/` |
| **`tests/**/*.py`** | **231** | Includes `tests/removal_evidence.py` |
| **Total Python (scripts + src + tests)** | **686** | `find scripts src tests -name '*.py'` |
| **Scanned for source-quality planner** | **455** | `276` src + `179` scripts (tests excluded) |
| **Consolidation `unknown` scripts** | **0** | `plan_script_consolidation` — all scripts bucketed |
| **Source-quality `unknown` verticals** | **102** | Flat vs Phase 6F (`192 → 102`); no further drop in 7C |

**Consolidation buckets (179 scripts):** maintenance 75 · audit_readonly 39 · break_glass 25 · lab_archive 17 · daily 11 · migration 6 · core_operator 4 · infrastructure_core 2 · compatibility_wrapper 0.

**Operator CLI surface (Phase 7):** `gmail-ingest`, `mirror-dashboard`, `refresh-dashboard`, plus 6B–6G subcommands — see [`OPERATOR_COMMAND_SURFACE.md`](../OPERATOR_COMMAND_SURFACE.md).

---

## 2. Top 30 largest Python files (production code)

Ranked by line count across **`src/` + `scripts/`** only (tests excluded). Category from `plan_source_quality` heuristics + manual triage.

| # | Path | Lines | Likely owner / category | Safe next action |
|---|------|------:|-------------------------|------------------|
| 1 | `src/.../core/research_automation.py` | 1683 | research / lab (planner: unknown) | **audit later** — large; subprocess to external tools; not daily CLI |
| 2 | `src/.../commercial/commercial_deal_promotion.py` | 1627 | commercial | **keep** — core promotion library; split only with tests |
| 3 | `src/.../leads/contacted_universe_audit.py` | 1239 | leads / outbound audit | **keep** — post-send exclusion truth |
| 4 | `src/.../mart_core_postgres_migrate.py` | 1181 | postgres_mirror (unknown) | **extract library** — shared with sync/migrate; parked ops |
| 5 | `src/.../lead_research/institution_grouping_audit.py` | 1165 | leads / research QA | **keep** — audit lane |
| 6 | `scripts/reports/generate_client_report.py` | 1111 | reports | **park** — client pack; not daily operator |
| 7 | `src/.../dashboard_postgres_sync.py` | 1048 | postgres_mirror (unknown) | **keep** — mirror orchestrator; CLI wraps it |
| 8 | `src/.../tatiana_copilot/openai_chat_generator.py` | 1028 | tatiana_lab | **park** — optional ML/API deps |
| 9 | `src/.../lead_research/legacy_contacts_2016_2019.py` | 979 | leads / archive | **keep** — library; script removed Phase 5R |
| 10 | `scripts/migrate/sqlite_archive_to_postgres.py` | 956 | migration / break-glass | **park** — scratch Postgres only |
| 11 | `src/.../streamlit_prioridad_pages.py` | 934 | streamlit_ui | **park** — legacy UI; API dashboard preferred |
| 12 | `src/.../core/outbound/broad_marketing_contacts.py` | 866 | outbound | **keep** — volume lane core |
| 13 | `src/.../supplier_workbook.py` | 851 | suppliers | **audit later** — domain-specific |
| 14 | `src/.../qa/contacted_lead_overlap.py` | 824 | qa / outbound | **keep** — CLI `audit-overlap` |
| 15 | `src/.../warm_case_sender_rules.py` | 807 | warm_cases | **keep** — promotion rules |
| 16 | `src/.../archive_outreach_queue.py` | 803 | archive_lane | **audit later** — archive send path |
| 17 | `src/.../qa/conversation_intelligence.py` | 793 | qa | **keep** — export library |
| 18 | `src/.../leads/new_customer_research.py` | 790 | leads | **keep** |
| 19 | `src/.../campaigns/presentacion_origenlab_quality.py` | 785 | campaigns / wave | **park** — dated campaign wave |
| 20 | `src/.../email_classification_qa.py` | 767 | qa (unknown) | **split** — library vs CLI concerns |
| 21 | `src/.../postgres_dashboard_api/schemas.py` | 725 | postgres_api | **keep** — read models for mirror API |
| 22 | `scripts/commercial/build_commercial_intel_v1.py` | 716 | commercial / break-glass | **park** — break-glass rebuild |
| 23 | `src/.../campaigns/cyber_outreach_campaign.py` | 691 | campaigns / wave | **park** — OPS_MAINT wave |
| 24 | `src/.../campaigns/cyber_campaign_context_audit.py` | 676 | campaigns / wave | **park** |
| 25 | `src/.../campaigns/cyber_campaign_quality.py` | 669 | campaigns / wave | **park** |
| 26 | `src/.../qa/daily_health_report.py` | 656 | qa | **keep** — CLI `daily-health` |
| 27 | `scripts/migrate/sqlite_document_master_to_postgres.py` | 654 | migration | **park** |
| 28 | `src/.../campaigns/presentacion_origenlab_campaign.py` | 646 | campaigns / wave | **park** |
| 29 | `src/.../equipment_deepsearch_vetted_queue.py` | 644 | equipment (unknown) | **audit later** — taxonomy label candidate |
| 30 | `src/origenlab_email_pipeline/cli.py` | 637 | operator_cli (unknown) | **split** — Phase 8 PR A |

**Largest test modules (for awareness, not refactor targets):** `tests/test_research_automation.py` (1380), `tests/test_build_archive_send_batch.py` (1253), `tests/test_sync_dashboard_postgres_mirror.py` (772).

---

## 3. Top remaining `unknown` verticals (102 files)

Planner heuristic only — **do not change taxonomy in Phase 8A**. Representative paths and **proposed labels** for a future round:

| Proposed label | Representative paths | Count (approx.) | Notes |
|----------------|---------------------|----------------:|-------|
| **`operator_cli`** | `cli.py`, `operator_status_report.py`, `operator_copy_es.py` | ~5 | Now includes multi-step workflows (7A–7C) |
| **`postgres_mirror`** | `mart_core_postgres_migrate.py`, `dashboard_postgres_sync.py`, `*_postgres_mirror.py`, `scripts/sync/*`, `scripts/migrate/*` | ~15 | Parked; CLI `mirror-dashboard` / `refresh-dashboard` |
| **`equipment_first`** | `equipment_*_queue.py`, `equipment_opportunity_mirror.py`, `scripts/sync/load_equipment_opportunity_mirror.py` | ~8 | Equipment-first operator lane |
| **`core_infrastructure`** | `db.py`, `parse_mbox.py`, `attachment_extract.py`, `canonical_operational_sql.py`, `core/reports_out.py` | ~10 | Shared OLTP / ingest primitives |
| **`qa_exports`** | `scripts/qa/export_*.py`, `validate_*.py`, `audit_*.py` still tagged unknown | ~25 | Many are daily/read-only; keywords miss `export_`/`validate_` |
| **`campaign_scripts`** | `scripts/qa/build_cyber_*.py`, `build_presentacion_*.py` | ~6 | Thin script wrappers over `src/.../campaigns/*` |
| **`research_lab`** | `scripts/research/run_deep_research_prospecting.py`, `verify_research_candidate_evidence.py`, `core/research_automation.py` | ~5 | Not daily outbound |
| **`streamlit_read`** | `read/today_workspace.py`, `streamlit_*` helpers | ~4 | Legacy read UI |
| **`purge_break_glass`** | `scripts/tools/purge_*.py`, `archive_reports_out_generated.py` | ~5 | Already in SCRIPT_MAP break-glass |
| **`misc_root_src`** | `email_business_filters.py`, `business_filter_rules.py`, `bi_views.py`, `marketing_contact_noise.py` | ~19 | Triage into outbound/mart/qa |

**Action (Phase 8A):** Phase **8C** taxonomy round — update `plan_source_quality.py` keyword maps only; no file moves.

### Phase 8C complete (2026-06-03)

- **Scope:** taxonomy-only — `scripts/qa/plan_source_quality.py` + path-only tests; **no runtime behavior change**, no file moves/deletes.
- **Source-quality `unknown` verticals:** **102 → 51** (−51; planner re-run with `--top 100`).
- **Artifact:** `reports/out/active/current/plan_source_quality_after_phase8c.json` (local, gitignored).
- **New buckets:** `operator_cli`, `postgres_mirror`, `equipment_first`, `core_infrastructure`, `qa_exports`, `campaign_scripts`, `research_lab`, `streamlit_read`, `purge_break_glass`; conservative misc root `src` → `outbound` / `qa` where obvious.

---

## 4. Risk hotspots

Text scan of **`src/` + `scripts/`** (read-only). Counts are files with **any** keyword match (overlap expected).

| Signal | Files (approx.) | Classification guidance |
|--------|----------------:|-------------------------|
| **`--apply` in source** | 29 total (**20 scripts**) | Dry-run default scripts vs explicit `--apply` mutators |
| **Destructive keywords** (`DELETE`, `TRUNCATE`, `DROP`, `--replace`, `--rebuild`, `purge_`) | 80 | Mix of mart rebuild, migrate loaders, purges |
| **Gmail / IMAP** | 153 | Ingest + Sent preflight + audits — not send unless break-glass |
| **Postgres / Alembic** | 77 | **Parked** — mirror, verify, migrate |
| **SQLite / path settings** | 273 | Expected — operational OLTP truth |

### `--apply` scripts (20 — from consolidation planner)

| Script | Class |
|--------|-------|
| `scripts/leads/run_current_campaign_pipeline.py` | daily / advanced |
| `scripts/leads/mark_outreach_state.py` | daily / advanced |
| `scripts/leads/import_lead_contact_research_csv.py` | daily / advanced |
| `scripts/leads/backfill_contacted_from_gmail_sent.py` | advanced |
| `scripts/leads/reconcile_lead_upstream.py` | advanced |
| `scripts/leads/dedupe_lead_master.py` | advanced |
| `scripts/tools/flag_ndr_bounces_from_contacto.py` | break-glass (filtered apply) |
| `scripts/tools/archive_reports_out_generated.py` | break-glass |
| `scripts/tools/purge_*.py` (3) | break-glass |
| `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` | break-glass |
| `scripts/maintenance/dedupe_canonical_gmail_messages.py` | break-glass |
| `scripts/commercial/promote_*.py`, `update_commercial_deal_costs.py`, `apply_commercial_deal_schema_dry_run.py` | parked commercial |
| `scripts/commercial/promote_warm_cases_to_postgres.py` | parked Postgres |
| `scripts/sync/load_equipment_opportunity_mirror.py` | parked Postgres |
| `scripts/qa/plan_script_consolidation.py` | read-only planner (mentions `--apply` in docs scan) |

### Gmail / Postgres / SQLite touchpoints (operator-relevant)

| Area | Daily | Advanced | Break-glass | Parked |
|------|-------|----------|-------------|--------|
| **Gmail ingest** | CLI `gmail-ingest` → `05_workspace_gmail_imap_to_sqlite.py` | `--since-days`, raw script flags | `--replace-source` on ingest script | — |
| **SQLite mart** | — | CLI `build-mart`, `refresh-dashboard --apply` uses `--rebuild` | `build_business_mart.py --rebuild` | — |
| **Postgres mirror** | — | CLI `mirror-dashboard` (dry-run default) | `--allow-non-scratch-postgres`, migrate `--replace` | All `scripts/migrate/*`, `scripts/sync/*`, verifiers |
| **Send** | — | — | `send_inline_html_email_via_gmail_api.py` | — |

**Phase 7 note:** `refresh-dashboard` orchestrates Gmail ingest + mart `--rebuild` + safety + mirror — treat as **advanced/break-glass bundle**, plan-only by default.

---

## 5. Duplication / consolidation candidates

Observed patterns (no changes in 8A):

| Pattern | Where repeated | Consolidation idea |
|---------|----------------|-------------------|
| **Subprocess script chains** | `cli.py` (`refresh-dashboard`, `gmail-ingest`, `mirror-dashboard`), `refresh_outbound_safety_memory.py`, `run_current_campaign_pipeline.py`, `dashboard_postgres_sync.py`, `research_automation.py` | Shared `operator_runner` module with step logging + exit-code policy (PR C) |
| **Argparse boilerplate** | ~179 scripts + growing `cli.py` subparsers | Keep scripts as-is; extract CLI parsing into `operator_cli/` package (PR A) |
| **SQLite connect / settings** | `db.py`, `load_settings()`, per-script `ORIGENLAB_SQLITE_PATH` resolution | Already partially centralized — audit scripts that open `sqlite3` directly vs `origenlab_email_pipeline.db` |
| **Report output paths** | `reports/out/active/current/` hard-coded vs `core.reports_out` | Extend `reports_out` helpers; align new exports (planners already share classification) |
| **Postgres URL resolution** | `mart_core_postgres_migrate.resolve_postgres_url`, duplicate copies in each `scripts/migrate/sqlite_*_to_postgres.py`, `postgres_outbound_audit.py`, CLI env pre-check | Single import surface; migrate scripts become thin CLI wrappers (PR E) |
| **Scratch / cloud safety** | `assert_scratch_postgres_target`, CLI cloud-only `--allow-non-scratch-postgres` auto-flag | Document in OPERATOR_COMMAND_SURFACE; optional shared `postgres_target_policy` helper |
| **Campaign wave scripts** | `scripts/qa/build_cyber_*`, `build_presentacion_*` mirror `src/.../campaigns/*` | Park/document as OPS_MAINT; no daily CLI alias (PR D) |
| **Thin `if __name__` scripts** | Many `scripts/qa/*.py` import library `main` | Already healthy — prefer more library extraction over new scripts |

---

## 6. Suggested next PRs (ordered)

| PR | Scope | Rationale |
|----|-------|-----------|
| **A. Split `cli.py`** | `src/origenlab_email_pipeline/operator_cli/` — `main.py`, `gmail.py`, `mirror.py`, `refresh.py`, `parser.py` | **637 lines**, 3 multi-step workflows; tests already mock `run_subcommand` |
| **B. Source taxonomy round 2** | Planner-only keyword expansion in `plan_source_quality.py` | **102 unknown** unchanged since 6F; low risk if no file moves |
| **C. Shared runner utilities** | `run_step(name, argv)`, env gates, consistent `[step]` logging | Reduces duplication vs `refresh_outbound_safety_memory` + `refresh-dashboard` |
| **D. Park campaign-wave scripts** | Docs + SCRIPT_MAP tags for `build_cyber_*` / `build_presentacion_*` | Large `src/campaigns/*` + thin QA scripts; not daily |
| **E. Postgres migrate/verifier grouping** | Doc index + optional CLI subgroup (`origenlab mirror-*` already started) | 6 migration + 5 verify scripts; parked lane |
| **F. Tatiana/lab optional deps** | `uv` group boundaries; ensure daily `uv sync` does not require OpenAI/torch | 39 `tatiana_lab` vertical files; Streamlit copilot |

**Explicitly defer:** script deletes, `scripts/` directory reshuffles, behavior changes to ingest/mirror/send, Postgres `--apply` automation.

---

## 7. Phase 6 → 7 → 8 delta (operator surface)

| Phase | Added |
|-------|--------|
| **7A** | `gmail-ingest`, `gmail-ingest-folders`, `gmail-ingest-help` |
| **7B** | `mirror-dashboard` (dry-run default; cloud URL + non-scratch handling) |
| **7C** | `refresh-dashboard` (plan-only default; `--apply` orchestration) |

Consolidation **`unknown=0`** held through 7C. Source **`unknown=102`** through 8A/8B; **Phase 8C** taxonomy dropped it to **51** (planner-only).

---

## 8. Verification (this audit)

```bash
cd apps/email-pipeline
uv run pytest tests/test_plan_source_quality_taxonomy.py tests/test_operator_cli.py tests/test_operator_entrypoint_contracts.py -q
# 85 passed (2026-06-03, after Phase 8C)
```

No Gmail, Postgres writes, or `--apply` executed during this audit.
