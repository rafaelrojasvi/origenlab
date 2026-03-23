# Scripts

Run from **`apps/email-pipeline/`** with `uv run python scripts/...` or `bash scripts/...`. Not installed as package entrypoints.

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
| [`verify_client_pack_consistency.py`](qa/verify_client_pack_consistency.py) | Cross-check `client_pack_latest/summary.json`, SQLite, `leads_top20_for_client_report.csv`, hunt + readiness CSVs | [`reports/out/client_pack_latest/summary.json`](../reports/out/README.md), `ORIGENLAB_SQLITE_PATH`, [`reports/out/active/`](../reports/out/README.md) CSVs listed in [`operational_trust.leads_active_paths`](../src/origenlab_email_pipeline/operational_trust.py) | stdout | After pack build or when pack/DB/active CSVs change | **Yes** (critical checks) |
| [`audit_operational_trust.py`](qa/audit_operational_trust.py) | Scorecard: cohort, readiness nulls, hunt taxonomy, pack freshness, audit MD DB path, merged vs current hunt IDs | `active/` CSVs, pack `summary.json`, [`docs/generated/CONTACT_READINESS_AUDIT.md`](../docs/generated/CONTACT_READINESS_AUDIT.md), SQLite path for provenance | [`reports/out/active/operational_trust_scorecard.json`](../reports/out/README.md), [`docs/generated/operational_trust_scorecard.md`](../docs/generated/operational_trust_scorecard.md) | Same as gate / CI spot checks | **Yes** (critical checks) |
| [`check_evidence_links.py`](qa/check_evidence_links.py) | `http(s)` URL format + live HEAD/GET with thresholds | `source_url` in top20; hunt columns `url_fuente`, `url_contacto_compras`, `url_transparencia_oirs`, `url_pagina_laboratorio`, `url_perfil_comprador`, `url_evidencia_*` | stdout | Full publication validation (or skip via gate flag for internal-only) | **Yes** if run and thresholds exceeded; also fails if **no** URLs are collected (checked count 0) |

**Docs:** [RUNBOOK §4](../docs/RUNBOOK.md#m-eprun-publish-qa), [REPORTING — QA leads](../docs/REPORTING.md#m-eprep-leads-qa), [ARCHITECTURE — trust layer](../docs/ARCHITECTURE.md#m-eparch-qa-trust).
