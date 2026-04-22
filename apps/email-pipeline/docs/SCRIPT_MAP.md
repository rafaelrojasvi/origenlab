# Email pipeline — script map (canonical operator index)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-24

**This document is the canonical operator map** for outbound and campaign work. It is **navigation and safety labeling only** — behavior lives in code and in [`RUNBOOK.md`](RUNBOOK.md).

**Canonical working directory:** `apps/email-pipeline/` (`cd apps/email-pipeline`).

**Reproducibility, safety, inventory:** [REPRODUCIBILITY.md](REPRODUCIBILITY.md) (machine setup) · [CRUD_SAFETY.md](CRUD_SAFETY.md) (read/create/update/delete rules) · [SCRIPT_INVENTORY.md](SCRIPT_INVENTORY.md) (group-level script classification) · read-only [check_reproducibility.py](../scripts/qa/check_reproducibility.py) · read-only [plan_reports_out_cleanup.py](../scripts/qa/plan_reports_out_cleanup.py) (scan `reports/out` before any cleanup; does not change files; buckets include `active_current`, `active_workspace_misc`, `client_pack_latest`, tmp/lab/archive/reference, etc.) · [archive_reports_out_generated.py](../scripts/tools/archive_reports_out_generated.py) (optional **move** of selected generated files into `archive/manual_cleanup/…`; **dry-run** default, `--apply` + `--archive-slug` to execute; no deletes) · read-only [plan_script_consolidation.py](../scripts/qa/plan_script_consolidation.py) (classify `scripts/` sprawl before deprecating, wrapping, or deleting entrypoints; does not change files) · read-only [plan_source_quality.py](../scripts/qa/plan_source_quality.py) (heuristic `src/` + `scripts/` size/vertical scan; planning only) · [`QUALITY_AND_REFACTOR_STRATEGY.md`](QUALITY_AND_REFACTOR_STRATEGY.md) (refactor rules; **new** code should **prefer** `core.*` imports where re-exports exist; no mass rewrites yet).

**Root `scripts/*.py` lead-account shims** (`build_lead_account_rollup.py`, `audit_lead_org_quality.py`, `match_lead_accounts_to_existing_orgs.py`, `validate_lead_account_rollup.py`) are **compatibility wrappers** to `scripts/leads/advanced/…`—**not** deletion targets until doc/test/operator paths are migrated; see file docstrings. Pure env redaction utilities: [`core/safety.py`](../src/origenlab_email_pipeline/core/safety.py).

**Contracts (tests, not a second truth):** [`test_operator_entrypoint_contracts.py`](../tests/test_operator_entrypoint_contracts.py) runs ``--help`` on the **named** daily/ingest/QA/planner entrypoints (including the reports-out archive tool), asserts top-of-file warnings on the break-glass set (aligned to tables below), and checks the four root compatibility wrappers. Regressions require updating that test for intentional path/contract changes; **deleting** scripts is still a **separate** approved change.

**Canonical campaign workspace:** fresh inputs and outputs for the two outbound lanes belong in **`reports/out/active/current/`**. Other paths under `reports/out/active/` (and most of `reports/out/archive/`) are **evidence, history, or ad-hoc exports** — not the default place to pick up “today’s” CSV for DeepSearch or send lists. (Stage 6C1) Volume marketing **processing** helpers for ``process_broad_marketing_contacts`` live in ``core.outbound.broad_marketing_contacts``; the **script** remains the supported entrypoint (CSV contracts unchanged). (Stage 6C2) **Do-not-repeat master** merge/summary formatting for ``export_do_not_repeat_master.py`` lives in ``core.outbound.do_not_repeat_master``; the **script** remains the daily entrypoint; **read-only** on SQLite; output filenames and JSON/CSV contract unchanged.

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

---

## Two workspace prep stories (do not confuse)

| Script | Purpose | When to use |
|--------|---------|-------------|
| [`scripts/qa/prepare_outbound_campaign_workspace.py`](../scripts/qa/prepare_outbound_campaign_workspace.py) | Initializes / archives **`reports/out/active/current/`** and campaign manifest for **volume + precision outbound lanes** | **Before** a new campaign round in `active/current/` |
| [`scripts/leads/advanced/prepare_active_workspace.py`](../scripts/leads/advanced/prepare_active_workspace.py) | Cleans **`reports/out/active/`** for **legacy weekly lead focus** (shortlist, hunt, deepsearch CSV hygiene; archives extras) | **Lead pipeline / REPORTING** workflows — see [`REPORTING.md`](REPORTING.md), [`leads/LEAD_PIPELINE.md`](leads/LEAD_PIPELINE.md) |

If you only care about the **two daily outbound lanes**, prefer **`prepare_outbound_campaign_workspace.py`**. If you are maintaining **hunt sheets + unified active CSVs**, you may still need **`prepare_active_workspace.py`** — read both docstrings before picking one.

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
| `scripts/qa/validate_sqlite_archive_for_postgres.py` | OPS_MIGRATE | Read-only / pre-migrate validation |
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

These are **not** the volume or precision daily lanes; see [`dataset/TATIANA_PILOT_WORKFLOW.md`](dataset/TATIANA_PILOT_WORKFLOW.md) and [`RUNBOOK.md`](RUNBOOK.md).

---

<a id="one-time-maintenance--alternate-lanes"></a>

## Archive lane & maintenance (ARCHIVE_LANE / OPS_MAINT / CONSOLIDATE)

| Path | Tag | Role |
|------|-----|------|
| `scripts/leads/build_archive_send_batch.py` | ARCHIVE_LANE | **`contact_master`** / archive send batch lane |
| `scripts/leads/precheck_archive_shortlist_commercial.py` | ARCHIVE_LANE | Archive commercial precheck |
| `scripts/leads/build_manual_html_outreach_batch.py` | CONSOLIDATE | Manual HTML package (files only); overlaps “send prep” with API sender |
| `scripts/leads/mark_outreach_state.py` | OPS_CORE | Manual single-row **`outreach_contact_state`** edits |
| `scripts/leads/import_operator_outreach_blocklist.py` | OPS_CORE | Blocklist → suppressions |
| `scripts/leads/add_manual_contact_suppressions.py` | OPS_CORE | Manual suppression adds |
| `scripts/qa/export_all_known_marketing_contacts.py` | CONSOLIDATE | Known-marketing export; overlaps part of do-not-repeat master story |
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
| `scripts/migrate/sqlite_archive_to_postgres.py` | **TRUNCATE** / load on Postgres target |
| `scripts/migrate/sqlite_document_master_to_postgres.py` | **DELETE** / load on Postgres target |
| `scripts/migrate/sqlite_outbound_sidecars_to_postgres.py` | **DELETE** / load on Postgres target |
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
