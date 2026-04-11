# Scripts

## Quick navigation

| Kind | What to use | Notes |
|------|-------------|--------|
| **Stable operational entrypoints** | Ingest ([`ingest/`](ingest/)), [`mart/build_business_mart.py`](mart/build_business_mart.py), [`commercial/build_commercial_intel_v1.py`](commercial/build_commercial_intel_v1.py), [`leads/run_leads_operational_stack.sh`](leads/run_leads_operational_stack.sh), QA ([`qa/publish_gate.py`](qa/publish_gate.py) and table below) | Procedures and ordering: [`docs/RUNBOOK.md`](../docs/RUNBOOK.md), schema map: [`docs/pipeline/SCHEMA_OWNERSHIP.md`](../docs/pipeline/SCHEMA_OWNERSHIP.md) |
| **Lead-account (canonical)** | [`leads/build_lead_account_rollup.py`](leads/build_lead_account_rollup.py), [`leads/match_lead_accounts_to_existing_orgs.py`](leads/match_lead_accounts_to_existing_orgs.py), [`leads/validate_lead_account_rollup.py`](leads/validate_lead_account_rollup.py), [`leads/audit_lead_org_quality.py`](leads/audit_lead_org_quality.py) | Same code as root wrappers; detail: [`docs/leads/LEAD_ACCOUNT_LAYER.md`](../docs/leads/LEAD_ACCOUNT_LAYER.md) |
| **Compatibility wrappers** | Root-level `scripts/build_lead_account_rollup.py`, `scripts/match_…`, etc. | Delegate to `leads/`; keep for bookmarks and old shell one-liners |
| **One-off / exploratory** | [`tools/`](tools/), [`validation/`](validation/) (phase checks), [`ml/`](ml/), some [`dataset/`](dataset/) | Not the main weekly path; useful for debugging or optional ML |

**Execution:** always from **`apps/email-pipeline/`** — **`uv run python scripts/...`** or **`uv run bash scripts/...`** (see below).

## How to run

From **`apps/email-pipeline/`** (monorepo: `cd apps/email-pipeline`):

- **Preferred:** `uv run python scripts/...` or `uv run bash scripts/...` so the editable package and dependency groups resolve consistently.
- Script locations (e.g. `scripts/qa/publish_gate.py`, `scripts/leads/build_lead_account_rollup.py`) are part of the **operational contract**: documented in [`docs/RUNBOOK.md`](../docs/RUNBOOK.md), [`docs/pipeline/SCHEMA_OWNERSHIP.md`](../docs/pipeline/SCHEMA_OWNERSHIP.md), and regression-tested under `tests/test_critical_script_paths.py`. **If you move a script, update docs and that test in the same change.**
- Subfolder scripts that use `sys.path` should resolve the app root with `Path(__file__).resolve().parents[2]` when the file is `scripts/<subdir>/tool.py` (not `parent.parent`, which pointed at `scripts/` only). Shared reference: [`_bootstrap.py`](_bootstrap.py) exposes `APP_ROOT` / `SCRIPTS_DIR` for future imports.

## Lead-account layer (rollup + mart match)

**Canonical implementations** (same `sys.path` pattern as other `scripts/leads/*.py`):

- [`leads/build_lead_account_rollup.py`](leads/build_lead_account_rollup.py) — full rollup rebuild  
- [`leads/match_lead_accounts_to_existing_orgs.py`](leads/match_lead_accounts_to_existing_orgs.py) — match accounts → `organization_master`  
- [`leads/validate_lead_account_rollup.py`](leads/validate_lead_account_rollup.py) — sanity checks  
- [`leads/audit_lead_org_quality.py`](leads/audit_lead_org_quality.py) — org_name quality audit  

**Thin compatibility wrappers** at the repo’s `scripts/` root ([`build_lead_account_rollup.py`](build_lead_account_rollup.py), etc.) delegate to the `leads/` copies so older commands and bookmarks keep working. Prefer documenting `scripts/leads/…` for new material.  

## Where to read

| Need | Doc |
|------|-----|
| Commands and workflows | [docs/RUNBOOK.md](../docs/RUNBOOK.md#m-eprun-path) (incl. [publish gate QA](../docs/RUNBOOK.md#m-eprun-publish-qa)) |
| Data flow and layout | [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) |
| Leads / accounts | [docs/leads/LEAD_PIPELINE.md](../docs/leads/LEAD_PIPELINE.md), [docs/leads/LEAD_ACCOUNT_LAYER.md](../docs/leads/LEAD_ACCOUNT_LAYER.md) |

## Folder map

| Directory | Role |
|-----------|------|
| `ingest/` | PST → mbox → SQLite → JSONL |
| `mart/` | Business mart, batch overview, open report |
| `reports/` | Client report, `run_all_reports.py`, `run_all.sh` |
| `validation/` | Phase checks, attachment text extraction |
| `ml/` | Embeddings, clusters, `email_ml_explore` |
| `dataset/` | Voice cohort metrics, Tatiana/Vivanco DB audit, stratified review CSV export |
| `tools/` | Inspect DB, dedupe, env checks |
| `pipeline/` | Cross-layer runs (e.g. aligned stack) |
| `leads/` | Lead scoring, matching, audits |
| `qa/` | Operational trust / publication gate ([`publish_gate.py`](qa/publish_gate.py) y scripts relacionados; ver tabla abajo) |

<a id="m-scripts-qa"></a>
## `scripts/qa/` — operational trust (publication gate)

Run from **`apps/email-pipeline/`**. Exit code **`0`** = no **critical** check failed in that script; **`1`** = at least one critical check failed. Non-critical failures print `FAIL` without failing the process alone (see [`operational_trust.py`](../src/origenlab_email_pipeline/operational_trust.py) `TrustCheck.critical`).

| Script | Purpose | Main inputs | Main outputs | When to run | Blocking? |
|--------|---------|-------------|--------------|-------------|-----------|
| [`publish_gate.py`](qa/publish_gate.py) | Runs verify → audit → evidence (unless `--skip-evidence-http`) | Same as substeps; `--db`, `--max-pack-age-hours`, evidence flags | stdout + scorecard files from audit step | Before external handoff of client pack + operational lead CSVs | **Yes** (aggregate) |
| [`verify_client_pack_consistency.py`](qa/verify_client_pack_consistency.py) | Pack vs DB + top20 vs hunt/readiness/DB (hunt/readiness **cohort partition** is only in [`audit_operational_trust.py`](qa/audit_operational_trust.py) / full gate) | [`reports/out/client_pack_latest/summary.json`](../reports/out/README.md), `ORIGENLAB_SQLITE_PATH`, [`reports/out/active/`](../reports/out/README.md) CSVs in [`operational_trust.leads_active_paths`](../src/origenlab_email_pipeline/operational_trust.py) | stdout | After pack build or when pack/DB/active CSVs change | **Yes** (critical checks) |
| [`audit_operational_trust.py`](qa/audit_operational_trust.py) | Scorecard: cohort, readiness nulls, hunt taxonomy, pack freshness, audit MD DB path, merged vs current hunt IDs | `active/` CSVs, pack `summary.json`, [`docs/generated/CONTACT_READINESS_AUDIT.md`](../docs/generated/CONTACT_READINESS_AUDIT.md), SQLite path for provenance | [`reports/out/active/operational_trust_scorecard.json`](../reports/out/README.md), [`docs/generated/operational_trust_scorecard.md`](../docs/generated/operational_trust_scorecard.md) | Same as gate / CI spot checks | **Yes** (critical checks) |
| [`check_evidence_links.py`](qa/check_evidence_links.py) | `http(s)` URL format + live HEAD/GET with thresholds | `source_url` in top20; hunt columns `url_fuente`, `url_contacto_compras`, `url_transparencia_oirs`, `url_pagina_laboratorio`, `url_perfil_comprador`, `url_evidencia_*` | stdout | Full publication validation (or skip via gate flag for internal-only) | **Yes** if run and thresholds exceeded; also fails if **no** URLs are collected (checked count 0) |
| [`export_candidate_audit.py`](qa/export_candidate_audit.py) | Read-only CSV: sample **`lead_master`** + **`contact_master`** rows through the **same** [`candidate_export_gate`](../src/origenlab_email_pipeline/candidate_export_gate.py) as Cola / `export_marketing_from_contact_master` (`eligible`, `reject_reasons`, `*_hit` flags) | SQLite (`--db`), limits | CSV path (`--out`) | Spot checks, leakage review, parity baselines | **No** (informational; not the publish gate) |

**Docs:** [RUNBOOK §4](../docs/RUNBOOK.md#m-eprun-publish-qa), [RUNBOOK — cold export gate](../docs/RUNBOOK.md#m-eprun-cold-export-gate), [REPORTING — QA leads](../docs/REPORTING.md#m-eprep-leads-qa), [ARCHITECTURE — trust layer](../docs/ARCHITECTURE.md#m-eparch-qa-trust), [ARCHITECTURE — export eligibility](../docs/ARCHITECTURE.md#m-eparch-export-gate).
