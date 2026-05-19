# Email pipeline — script map (canonical operator index)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-05-19

**This document is the canonical operator map** for outbound and campaign work. It is **navigation and safety labeling only** — behavior lives in code and in [`RUNBOOK.md`](RUNBOOK.md).

**Canonical working directory:** `apps/email-pipeline/` (`cd apps/email-pipeline`).

**Reproducibility, safety, inventory:** [REPRODUCIBILITY.md](REPRODUCIBILITY.md) (machine setup) · [CRUD_SAFETY.md](CRUD_SAFETY.md) (read/create/update/delete rules) · [SCRIPT_INVENTORY.md](SCRIPT_INVENTORY.md) (group-level script classification) · read-only [check_reproducibility.py](../scripts/qa/check_reproducibility.py) · read-only [plan_reports_out_cleanup.py](../scripts/qa/plan_reports_out_cleanup.py) (scan `reports/out` before any cleanup; does not change files; buckets include `active_current`, `active_workspace_misc`, `client_pack_latest`, tmp/lab/archive/reference, etc.) · [archive_reports_out_generated.py](../scripts/tools/archive_reports_out_generated.py) (optional **move** of selected generated files into `archive/manual_cleanup/…`; **dry-run** default, `--apply` + `--archive-slug` to execute; no deletes) · read-only [plan_script_consolidation.py](../scripts/qa/plan_script_consolidation.py) (classify `scripts/` sprawl before deprecating, wrapping, or deleting entrypoints; does not change files) · read-only [plan_source_quality.py](../scripts/qa/plan_source_quality.py) (heuristic `src/` + `scripts/` size/vertical scan; planning only) · [`QUALITY_AND_REFACTOR_STRATEGY.md`](QUALITY_AND_REFACTOR_STRATEGY.md) (refactor rules; **new** code should **prefer** `core.*` imports where re-exports exist; no mass rewrites yet).

**Stage 6D1 (reports / `reports/out`):** path **classification** and planner aggregations are shared in [`core/reports_out.py`](../src/origenlab_email_pipeline/core/reports_out.py); [`plan_reports_out_cleanup.py`](../scripts/qa/plan_reports_out_cleanup.py) and [`archive_reports_out_generated.py`](../scripts/tools/archive_reports_out_generated.py) remain the **operator entrypoints**; archiver **dry-run** default and move-only semantics are unchanged in intent.

**Stage 6E1 (Tatiana / lab):** **boundary doc only** — see [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md). Lab / Tatiana / `scripts/ml` are **not** the daily outbound lanes. **Parked Postgres/API/pilots index:** [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md). Source-quality planner (`plan_source_quality.py`) labels the `tatiana_lab` bucket for the paths listed there. Future **6E2** may refactor large Tatiana modules; 6E1 does **not** move or change implementation.

**Lead-account root shims:** four files under `scripts/*.py` are **`COMPATIBILITY_WRAPPER` / `COMPATIBILITY_ONLY`** — retained for bookmarks and old one-liners; **not preferred** for new operator commands or agent prompts. **Canonical implementations:** `scripts/leads/advanced/*` (table below). **Do not delete** wrappers until doc/test references migrate. Pure env redaction utilities: [`core/safety.py`](../src/origenlab_email_pipeline/core/safety.py).

**Contracts (tests, not a second truth):** [`test_operator_entrypoint_contracts.py`](../tests/test_operator_entrypoint_contracts.py) runs ``--help`` on the **named** daily/ingest/QA/planner entrypoints (including the reports-out archive tool), asserts top-of-file warnings on the break-glass set (aligned to tables below), and checks the four root compatibility wrappers. [`test_lead_compatibility_wrappers.py`](../tests/test_lead_compatibility_wrappers.py) locks wrapper→canonical mapping and SCRIPT_MAP labeling. Regressions require updating those tests for intentional path/contract changes; **deleting** scripts is still a **separate** approved change.

**Canonical campaign workspace:** fresh inputs and outputs for the two outbound lanes belong in **`reports/out/active/current/`**. Other paths under `reports/out/active/` (and most of `reports/out/archive/`) are **evidence, history, or ad-hoc exports** — not the default place to pick up “today’s” CSV for DeepSearch or send lists. Keep only intentional root reference files in `active/` (`outreach_contacted_all.csv`, `all_known_marketing_contacts_dedup.csv`) because some scripts use them as default auxiliary inputs. (Stage 6C1) Volume marketing **processing** helpers for ``process_broad_marketing_contacts`` live in ``core.outbound.broad_marketing_contacts``; the **script** remains the supported entrypoint (CSV contracts unchanged). (Stage 6C2) **Do-not-repeat master** merge/summary formatting for ``export_do_not_repeat_master.py`` lives in ``core.outbound.do_not_repeat_master``; the **script** remains the daily entrypoint; **read-only** on SQLite; output filenames and JSON/CSV contract unchanged.

**Rule:** Broad **volume marketing** rows must **not** go into **`lead_contact_research`** unless each row has a real **`lead_id`**. Use **`reviewed_marketing_contacts.csv`** → **`process_broad_marketing_contacts.py`** → **`send_ready_marketing.csv`**.

---

## Mental model: core / ops / lab / break-glass

Use this to separate *what you run daily* from *what can hurt you*:

| Bucket | What it is | Where it lives |
|--------|------------|----------------|
| **Core** | Policy and business logic: gate, CSV contracts, outbound preflight, state, suppressions, Gmail helpers | `src/origenlab_email_pipeline/` (Python package) — **not** run directly; imported by scripts and tests. **Re-export import surface (Stage 2A / 2B):** [`src/origenlab_email_pipeline/core/`](../src/origenlab_email_pipeline/core/) mirrors many modules under `core.outbound`, `core.gmail`, `core.leads` (``leads_schema``, ``lead_contact_research``, …), etc., without moving implementation yet. |
| **Ops** | Thin operator entrypoints: ingest, validate CSVs, export send lists, mark contacted, campaign wrapper | `scripts/**/*.py` (and shell drivers) — **normal daily work** when labeled below |
| **Lab** | Pilots, Tatiana drafting, ML exploration, niche campaign tooling — **not** the two daily lanes | `scripts/tatiana/`, `scripts/dataset/`, `scripts/ml/`, much of `scripts/leads/campaigns/`, some `leads/advanced/` |
| **Break-glass** | Can **send mail**, **purge SQLite**, **rebuild** large derived tables, **`--apply`** side effects, or **truncate/load Postgres** — use only with intent | Called out in [Break-glass scripts](#break-glass-scripts) |

**Runtime source of truth today:** **SQLite** (`ORIGENLAB_SQLITE_PATH` or default under `ORIGENLAB_DATA_ROOT`). **Gmail Workspace Sent** ingested into **`emails`** is required for outbound safety (shared gate + preflight). **Postgres** is **optional** (migration loaders, Alembic, optional outbound audit) — **not** the primary OLTP for daily lanes.

**Postgres env URLs:** commented template in [`.env.example`](../.env.example). **Alembic** resolves `ALEMBIC_DATABASE_URL` before `ORIGENLAB_POSTGRES_URL`; **migrate scripts** and **`--write-postgres-audit`** resolve `--postgres-url`, then `ORIGENLAB_POSTGRES_URL`, then `ALEMBIC_DATABASE_URL` — full table in [`RUNBOOK.md`](RUNBOOK.md#m-eprun-postgres-optional). **Always trial migrate loaders on scratch Postgres first** (they can truncate/delete target tables).

---

## Two workspace prep stories (do not confuse)

| Script | Purpose | When to use |
|--------|---------|-------------|
| [`scripts/qa/prepare_outbound_campaign_workspace.py`](../scripts/qa/prepare_outbound_campaign_workspace.py) | Initializes / archives **`reports/out/active/current/`** and campaign manifest for **volume + precision outbound lanes** | **Before** a new campaign round in `active/current/` |
| [`scripts/leads/advanced/prepare_active_workspace.py`](../scripts/leads/advanced/prepare_active_workspace.py) | Cleans **`reports/out/active/`** for **legacy weekly lead focus** (shortlist, hunt, deepsearch CSV hygiene; archives extras) | **Lead pipeline / REPORTING** workflows — see [`REPORTING.md`](REPORTING.md), [`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md) |

If you only care about the **two daily outbound lanes**, prefer **`prepare_outbound_campaign_workspace.py`**. If you are maintaining **hunt sheets + unified active CSVs**, you may still need **`prepare_active_workspace.py`** — read both docstrings before picking one.

---

## Lead-account scripts: canonical vs root wrappers

**Operator rule:** In **new** docs, runbooks, and agent prompts, use **`scripts/leads/advanced/…`** only. Root paths below are **COMPATIBILITY_WRAPPER** — same behavior via delegation; **not preferred** for new commands.

| Tag | Root path (COMPATIBILITY_ONLY) | Canonical target (use this) | Notes |
|-----|-------------------------------|-----------------------------|--------|
| `COMPATIBILITY_WRAPPER` | [`scripts/build_lead_account_rollup.py`](../scripts/build_lead_account_rollup.py) | [`scripts/leads/advanced/build_lead_account_rollup.py`](../scripts/leads/advanced/build_lead_account_rollup.py) | Rebuilds `lead_account_*`; break-glass DELETE pattern on rollup |
| `COMPATIBILITY_WRAPPER` | [`scripts/match_lead_accounts_to_existing_orgs.py`](../scripts/match_lead_accounts_to_existing_orgs.py) | [`scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py`](../scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py) | Match accounts → `organization_master` |
| `COMPATIBILITY_WRAPPER` | [`scripts/validate_lead_account_rollup.py`](../scripts/validate_lead_account_rollup.py) | [`scripts/leads/advanced/validate_lead_account_rollup.py`](../scripts/leads/advanced/validate_lead_account_rollup.py) | Rollup sanity checks |
| `COMPATIBILITY_WRAPPER` | [`scripts/audit_lead_org_quality.py`](../scripts/audit_lead_org_quality.py) | [`scripts/leads/advanced/audit_lead_org_quality.py`](../scripts/leads/advanced/audit_lead_org_quality.py) | Org name quality audit |

Detail: [`leads/LEAD_ACCOUNT_LAYER.md`](leads/LEAD_ACCOUNT_LAYER.md) · [`../scripts/README.md`](../scripts/README.md#lead-account-rollup-and-mart-matching).

---

## Daily lanes

### Volume marketing lane

1. Export do-not-repeat lists for DeepSearch.
2. Run DeepSearch; save reviewed output as **`reports/out/active/current/reviewed_marketing_contacts.csv`**.
3. Validate CSV shape, then process through the shared gate → **`send_ready_marketing.csv`** (and split files).
4. **Human send** (manual or optional Gmail API script — see [Break-glass scripts](#break-glass-scripts)).
5. Mark contacted + ingest **Sent** so the next run sees Gmail truth.

Canonical commands:

```bash
cd apps/email-pipeline
uv run python scripts/qa/export_do_not_repeat_master.py
uv run python scripts/qa/validate_campaign_csvs.py \
  --file reports/out/active/current/reviewed_marketing_contacts.csv \
  --kind marketing_contacts --strict
uv run python scripts/leads/process_broad_marketing_contacts.py
# Review send_ready_marketing.csv — then send (manual or optional Gmail API)
uv run python scripts/leads/mark_sent_batch_contacted.py \
  --batch-file ... --source ... --updated-by ...
uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados"
```

Use the real **`--batch-file` / `--source` / `--updated-by`** values from your run; see [`RUNBOOK.md`](RUNBOOK.md#m-eprun-daily-outbound). Discover Sent folder labels with `05_workspace_gmail_imap_to_sqlite.py --list-folders` if `"[Gmail]/Enviados"` does not match your mailbox.

### Precision lead lane

1. **Prepare** campaign workspace and queue.
2. DeepSearch saves **`reports/out/active/current/reviewed_deepsearch.csv`** (must include **`lead_id`**).
3. **Process reviewed** (imports into **`lead_contact_research`** when run with **`--apply`**).
4. Review **`send_ready.csv`**, send, then **post-send** / mark contacted + Sent ingest.

Canonical commands:

```bash
cd apps/email-pipeline
uv run python scripts/leads/run_current_campaign_pipeline.py --stage prepare \
  --campaign-slug YOUR_SLUG --queue-limit 50 --operator you@example.com
# DeepSearch → reports/out/active/current/reviewed_deepsearch.csv
uv run python scripts/leads/run_current_campaign_pipeline.py --stage process-reviewed --apply \
  --operator you@example.com
# Review send_ready.csv — send manually or via your usual path
uv run python scripts/leads/run_current_campaign_pipeline.py --stage post-send \
  --source YOUR_SLUG --operator you@example.com
```

Dry-run import first if your wrapper allows it without `--apply`; see [`RUNBOOK.md`](RUNBOOK.md) and `run_current_campaign_pipeline.py --help`.

---

## Classification legend (scripts)

| Tag | Meaning |
|-----|---------|
| **OPS_DAILY** | On the two daily outbound lanes or required the same week (ingest Sent, validate CSVs). |
| **OPS_CORE** | Infrastructure operators need regularly (blocklist, suppressions, workspace prep) — not always every send. |
| **OPS_AUDIT** | Read-only or hygiene; debugging trust, overlap, readiness. |
| **OPS_MAINT** | Lead pipeline, mart rebuild, commercial rebuild, validation phases — **not** the two lanes. |
| **OPS_MIGRATE** | SQLite → Postgres or pre-checks — **optional** path. |
| **LAB** | Tatiana / ML / pilot / niche campaign tooling. |
| **CONSOLIDATE** | Overlaps another script’s job; docs pick a primary story. |
| **ARCHIVE_LANE** | Archive (`contact_master`) batch lane — still supported, not “daily mental model”. |
| **BREAK_GLASS** | Can send, purge, rebuild destructively, or **`--apply`** with high blast radius — see table below. |

Legacy tags **KEEP_CORE** / **KEEP_AUDIT** in older prose map loosely to **OPS_CORE** / **OPS_AUDIT**.

---

## Ops — daily lane scripts (OPS_DAILY / OPS_CORE)

| Path | Tag | Role | Typical outputs / notes |
|------|-----|------|-------------------------|
| `scripts/qa/export_do_not_repeat_master.py` | OPS_DAILY | Merge “do not repeat” emails for DeepSearch + volume processor | `reports/out/active/current/do_not_repeat_master.{csv,txt}`, `do_not_repeat_summary.json` |
| `scripts/qa/export_outreach_contacted_all.py` | OPS_DAILY | Export auxiliary contacted-all list (Sent + blocking outreach state) | `reports/out/active/outreach_contacted_all.csv` |
| `scripts/qa/refresh_outbound_safety_memory.py` | OPS_DAILY | Run canonical anti-repeat auxiliary refresh + strict checks (stops on first hard failure) | Combined step runner for contacted-all, all-known, DNR, strict coverage, hygiene, readiness |
| `scripts/qa/validate_contacted_csv_coverage.py` | OPS_DAILY | Strict overlap of auxiliary contacted CSVs vs Sent / gate inputs (`--strict` in refresh chain) | stdout / exit code; invoked by `refresh_outbound_safety_memory.py` |
| `scripts/research/run_deep_research_prospecting.py` | OPS_DAILY | Automated research automation (heavy weekly/off-peak, light daily) → review-ready volume batch (no send) | Writes timestamped `research_automation/<ts>/` artifacts, validates/processes, **stops before send**; `--research-mode heavy|light`; supports `--sector`, `--day-rotation`, `--daily-mode`; optional read-only `--run-contacted-coverage-check`; guardrails: `--max-candidates`, `--max-send-ready`, `--fail-on-over-limit`; compact-seed caps: `--max-seed-email-sample`, `--max-seed-institutions`, `--max-seed-domains`; presets: `--tpm-safe`, `--tiny-run`; rate-limit controls: `--max-retries`, `--initial-backoff-seconds`, `--max-backoff-seconds`, optional `--fallback-sector`; output mode: `--research-output-mode direct_csv|evidence_first`; **heavy is fail-closed true Deep Research only (`o4-mini-deep-research`/`o3-deep-research`)**. Warning: `web_search + gpt-4o-mini` is not Deep Research heavy mode. |
| `scripts/qa/validate_campaign_csvs.py` | OPS_DAILY | CSV contracts (`marketing_contacts`, `reviewed_deepsearch`, `send_ready`, etc.) | stdout / exit code; optional `--json-out` |
| `scripts/leads/process_broad_marketing_contacts.py` | OPS_DAILY | Validate, gate, split volume contacts | `marketing_*.csv`, `send_ready_marketing.csv`, `marketing_contacts_summary.json` |
| `scripts/leads/run_current_campaign_pipeline.py` | OPS_DAILY | Orchestrates precision lane (prepare / process-reviewed / post-send) | Files under `active/current/` |
| `scripts/qa/prepare_outbound_campaign_workspace.py` | OPS_DAILY | Initializes/archives **`active/current`** + campaign manifest | Placeholder / manifest files |
| `scripts/leads/export_lead_contact_research_queue.py` | OPS_DAILY | Exports **`research_queue.csv`** for lead DeepSearch | `active/current/research_queue.csv` (when used with pipeline) |
| `scripts/leads/import_lead_contact_research_csv.py` | OPS_CORE | Applies reviewed DeepSearch into **`lead_contact_research`** | DB writes (precision lane); **dry-run unless `--apply`** |
| `scripts/leads/export_next_marketing_recipients.py` | OPS_DAILY | **`send_ready.csv`** from `lead_master` + shared gate | Lead send list |
| `scripts/leads/mark_sent_batch_contacted.py` | OPS_DAILY | Post-send **`outreach_contact_state`** updates | Sidecar only |
| `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py` | OPS_DAILY | Gmail → **`emails`** (Sent / inbox) | Required for Sent-history truth |

**Optional send (BREAK_GLASS):** `scripts/qa/send_inline_html_email_via_gmail_api.py` — can send real mail; not auto-run. See below.

Research automation prompt templates: `prompts/deep_research_netnew_chile_marketing.txt` (heavy) and `prompts/light_research_netnew_chile_marketing.txt` (light). Planning + scheduling handoff: `docs/DEEP_RESEARCH_AUTOMATION_PLAN.md`, `scripts/research/cron_example.txt`.

**Core modules (not scripts):** `candidate_export_gate.py`, `marketing_export_context.py`, `outbound_core.py`, `outreach_contact_state.py`, `next_marketing_queue.py`, `csv_contracts.py`, `outbound_sent_preflight.py` — package **Core** infrastructure.

---

<a id="debug--audit-scripts-keepaudit--keepdebug"></a>

## Ops — audit & debug (OPS_AUDIT)

| Path | Tag | Role |
|------|-----|------|
| `scripts/qa/export_contacted_lead_overlap_audit.py` | OPS_AUDIT | Pre-import / pre-send overlap vs Sent, state, suppressions, lead/research |
| `scripts/qa/export_gate_audit_csv.py` | OPS_AUDIT | Per-candidate gate flags for lead (or archive) lane |
| `scripts/qa/export_outreach_volume_rollup.py` | OPS_AUDIT | Saturation metrics rollup (counts by source) |
| `scripts/qa/export_supplier_domain_false_positive_audit.py` | OPS_AUDIT | Supplier domain vs institutional false-positive hints |
| `scripts/qa/check_outbound_readiness.py` | OPS_AUDIT | Readiness / config checks |
| `scripts/leads/approve_reviewed_deepsearch_rows.py` | OPS_AUDIT | Promote manual-review rows to import (precision lane helper) |
| `scripts/leads/backfill_contacted_from_gmail_sent.py` | OPS_AUDIT | Backfill **`outreach_contact_state`** from Sent — **dry-run default; `--apply` writes** |
| `scripts/qa/print_outbound_run_summary.py` | OPS_AUDIT | Pretty-print outbound summary JSON |
| `scripts/qa/export_candidate_audit.py` | OPS_AUDIT | Sample rows through gate (informational) |
| `scripts/qa/check_reports_out_active_hygiene.py` | OPS_AUDIT | Warn/fail when `reports/out/active/` contains unexpected generated artifacts outside `current/` |
| `scripts/qa/build_equipment_first_opportunity_queue.py` | OPS_AUDIT | Equipment-first filter from `Licitacion_Publicada.csv` → `equipment_first_opportunity_queue_*.csv` (read-only on Gmail; writes reports only) |
| `scripts/qa/build_equipment_first_operator_queue.py` | OPS_AUDIT | Canonical operator queue + aligned `buyer_opportunity_ab_queue_*.csv` from equipment-first opportunity CSV (read-only cross-check vs DNR/Sent in SQLite) |
| `scripts/qa/build_buyer_opportunity_queue.py` | OPS_AUDIT | **LEGACY_DO_NOT_USE** — file header + docstring; legacy buyer/private-lab A/B cross-check **superseded** by `build_equipment_first_*`; retained for audit/tests only; stale `buyer_opportunity_crosscheck_*` must not drive export |
| `scripts/qa/operator_status.py` | OPS_AUDIT | **Read-only** operator snapshot: SQLite/Sent freshness, DNR files, canonical `active/current`, manifest warnings, verdict READY/CAUTION/BLOCKED |
| `scripts/qa/build_equipment_deepsearch_vetted_queue.py` | OPS_AUDIT | Gate `equipment_deep_research_opportunities_*.csv` → vetted queue (equipment-first + DNR/Sent/state); fails clearly if input missing |
| `scripts/qa/validate_sqlite_archive_for_postgres.py` | OPS_MIGRATE | Read-only / pre-migrate validation |
| `scripts/qa/audit_canonical_contacto_gmail.py` | OPS_AUDIT | Read-only: canonical Gmail vs legacy labdelivery vs other `emails` metrics |
| `scripts/qa/audit_email_classification_quality.py` | OPS_AUDIT | Read-only: heuristic commercial-type QA on canonical Gmail (keyword audit; not production labels) |
| `scripts/qa/audit_canonical_gmail_duplicates.py` | OPS_AUDIT | Read-only: duplicate `message_id` analysis within canonical Gmail rows |
| `scripts/maintenance/dedupe_canonical_gmail_messages.py` | **BREAK_GLASS** | **DELETE** duplicate canonical Gmail `emails` — dry-run default; `--apply --ack-sqlite-backup` |
| `scripts/qa/publish_gate.py` | OPS_AUDIT | Publication / trust gate (broader than outbound) |

**Overlap note:** **`export_do_not_repeat_master.py`** (operator *input list*) vs **`export_outreach_volume_rollup.py`** (*metrics*). Different jobs; do not delete one thinking it replaces the other.

---

## Lab scripts (LAB)

| Area | Examples |
|------|----------|
| Tatiana / drafting | `scripts/tatiana/*` |
| Dataset / cohort exports | `scripts/dataset/*` |
| ML / embeddings exploration | `scripts/ml/*` |
| Niche campaign reconciliations | `scripts/leads/campaigns/*` (e.g. DR50 payload flows) |

These are **not** the volume or precision daily lanes; see [`dataset/TATIANA_PILOT_WORKFLOW.md`](dataset/TATIANA_PILOT_WORKFLOW.md) and [`RUNBOOK.md`](RUNBOOK.md). **Scope / safety:** [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md) (Tatiana vs production outbound, OpenAI, `reports/out`). **Parked index (Postgres/API + pilots):** [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md).

---

<a id="one-time-maintenance--alternate-lanes"></a>

## Archive lane & maintenance (ARCHIVE_LANE / OPS_MAINT / CONSOLIDATE)

| Path | Tag | Role |
|------|-----|------|
| `scripts/leads/build_archive_send_batch.py` | ARCHIVE_LANE | **`contact_master`** / archive send batch lane |
| `scripts/leads/precheck_archive_shortlist_commercial.py` | ARCHIVE_LANE | Archive commercial precheck |
| `scripts/leads/build_manual_html_outreach_batch.py` | CONSOLIDATE | Manual HTML package (files only); overlaps “send prep” with API sender |
| `scripts/leads/mark_outreach_state.py` | OPS_CORE | Manual **`outreach_contact_state`** edits — **dry-run default**; **`--apply`** + `--updated-by`/`--operator`, `--source`/`--source-artifact`, `--reason` to write ([CRUD_SAFETY](CRUD_SAFETY.md#phase-2c-pilot-mark_outreach_statepy-implemented)) |
| `scripts/leads/import_operator_outreach_blocklist.py` | OPS_CORE | Blocklist → suppressions |
| `scripts/leads/add_manual_contact_suppressions.py` | OPS_CORE | Manual suppression adds |
| `scripts/qa/export_all_known_marketing_contacts.py` | OPS_CORE | Known-marketing dedup export across active/archive/reference sources (includes contacted-all by default) |
| `scripts/leads/advanced/prepare_active_workspace.py` | CONSOLIDATE | **Different** from `prepare_outbound_campaign_workspace.py` — see [Two workspace prep stories](#two-workspace-prep-stories-do-not-confuse) |
| `scripts/leads/advanced/export_marketing_from_contact_master.py` | ARCHIVE_LANE | Exploratory `contact_master` export |
| `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` | BREAK_GLASS | Bounce-driven sync — review evidence; **`--apply`** mutates state |

Many other `scripts/leads/*.py` (scoring, ChileCompra fetch, dedupe, mart match) are **OPS_MAINT** — see [`RUNBOOK.md`](RUNBOOK.md) and [`scripts/README.md`](../scripts/README.md).

---

## Break-glass scripts (BREAK_GLASS)

**File headers:** scripts in this table include a prominent **`SAFETY` / `SAFETY (break-glass)`** comment block at the top of the source file (in addition to this doc).

**Before running:** read `--help`, prefer dry-run defaults, and confirm **`ORIGENLAB_SQLITE_PATH`**. Do not use **`--apply`**, **send**, or **migrate** flags unless you intend to mutate production or target databases.

| Path | Why break-glass |
|------|-----------------|
| `scripts/qa/send_inline_html_email_via_gmail_api.py` | **Sends real email** via Gmail API when not in dry-run / build-only modes |
| `scripts/tools/purge_contact_emails_from_sqlite.py` | **Deletes** rows across many tables; **`--apply`** required to execute |
| `scripts/tools/purge_email_domain_from_sqlite.py` | **Domain-level purge**; **`--apply`** |
| `scripts/tools/purge_mailbox_from_sqlite.py` | **Mailbox purge**; **`--apply`** |
| `scripts/mart/build_business_mart.py` | Rebuild pattern **deletes** mart tables before rebuild |
| `scripts/commercial/build_commercial_intel_v1.py` | Can **delete** / rebuild commercial facts |
| `scripts/migrate/sqlite_archive_to_postgres.py` | **TRUNCATE** / load on Postgres target (**EXPERIMENTAL_PARKED** — see [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md)) |
| `scripts/sync/sync_dashboard_postgres_mirror.py` | Postgres dashboard mirror load (**EXPERIMENTAL_PARKED**; not send truth) |
| `scripts/ops/refresh_operational_dashboard_stack.py` | Optional mart + mirror stack (**DASHBOARD_ONLY**; not CORE_DAILY) |
| `scripts/migrate/sqlite_document_master_to_postgres.py` | **DELETE** / load on Postgres target (**EXPERIMENTAL_PARKED**) |
| `scripts/migrate/sqlite_outbound_sidecars_to_postgres.py` | **DELETE** / load on Postgres target (**EXPERIMENTAL_PARKED**) |
| `scripts/migrate/sqlite_mart_core_to_postgres.py` | **DELETE** / load on Postgres `mart.contact_master`, `organization_master`, `opportunity_signals` (**EXPERIMENTAL_PARKED**) |
| `scripts/maintenance/dedupe_canonical_gmail_messages.py` | **DELETE** duplicate canonical Gmail `emails` — dry-run default; `--apply --ack-sqlite-backup` |
| `scripts/leads/advanced/build_lead_account_rollup.py` | **DELETE** + rebuild `lead_account_*` |
| `scripts/qa/sync_outreach_batch_from_ingested_bounces.py` | **`--apply`** updates suppressions / state |
| `scripts/tools/flag_ndr_bounces_from_contacto.py` | **`--apply`** writes suppressions |
| `scripts/tools/flag_reported_non_delivery_from_contacto.py` | **`--apply`** writes suppressions |
| `scripts/validation/extract_attachment_text.py` | May **delete** `attachment_extracts` during rebuild patterns |
| `scripts/tools/archive_reports_out_generated.py` | **`--apply`** **moves** files under `reports/out` to `archive/manual_cleanup/…` (no deletes) |

---

## Tests (pointer)

Outbound / campaign regression tests live under `tests/` (e.g. `test_run_current_campaign_pipeline.py`, `test_process_broad_marketing_contacts.py`, `test_validate_campaign_csvs.py`, `test_export_gate_audit_csv.py`). **Do not remove** tests when editing docs.

---

<a id="do-not-remove-safety-critical"></a>

## Do not remove (safety-critical)

- **Gate policy:** `candidate_export_gate.py` + `GateContext` inputs — do not change policy lightly.
- **SQLite sidecar:** `outreach_contact_state` — operator memory for “already contacted”.
- **Gmail Sent in SQLite:** `emails` rows for configured Sent folders — blocker truth for exports.
- **Suppressions:** `contact_email_suppression`, `contact_domain_suppression`, and import CLIs.
- **CSV validation:** `validate_campaign_csvs.py`, `csv_contracts.py`.
- **Do-not-repeat master:** `export_do_not_repeat_master.py` — volume lane input to DeepSearch.
- **Post-send marking:** `mark_sent_batch_contacted.py` (and pipeline `post-send` where used).
- **Precision research persistence:** `import_lead_contact_research_csv.py` — primary path for **`lead_contact_research`** from reviewed DeepSearch.

---

## Related docs

- [`RUNBOOK.md`](RUNBOOK.md) — full procedures, mailbox ingest, Docker, publish gate
- [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md) — lane semantics
- [`scripts/README.md`](../scripts/README.md) — folder map and QA table
- Postgres planning: [`pipeline/POSTGRES_SCHEMA_TARGET_V1.md`](pipeline/POSTGRES_SCHEMA_TARGET_V1.md), [`pipeline/POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md`](pipeline/POSTGRES_ARCHIVE_DATA_MIGRATION_PLAN_V1.md)
