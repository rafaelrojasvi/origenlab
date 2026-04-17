# Email Pipeline App Context

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-15

Primary context for [`apps/email-pipeline/`](../).

<a id="m-epapp-purpose"></a>
## Purpose

Transform archived email sources into structured, queryable data and reporting outputs for business analysis and client-facing insights.

<a id="m-epapp-tatiana"></a>
## Commercial drafting assistant (Tatiana copilot)

Optional **OrigenLab / Labdelivery** commercial-email support: retrieval over curated historical examples, guarded LLM draft generation, and **mandatory human review** (eval CSVs and **pilot** `pilot_review.csv`). There is **no** send path, webhook, or autonomous reply in this repo.

- Concept and commands: [`dataset/TATIANA_DRAFTING_COPILOT.md`](dataset/TATIANA_DRAFTING_COPILOT.md)
- **Pilot workflow** (timestamped `reports/out/*_tatiana_pilot_batch/`): [`dataset/TATIANA_PILOT_WORKFLOW.md`](dataset/TATIANA_PILOT_WORKFLOW.md)
- **OrigenLab drafting context** (`run_tatiana_pilot_batch.py --origenlab`, facts from `apps/web/src/data`): [`dataset/ORIGENLAB_COMMERCIAL_DRAFTING_CONTEXT.md`](dataset/ORIGENLAB_COMMERCIAL_DRAFTING_CONTEXT.md)
- Business claims must align with monorepo policy: [`../../../docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](../../../docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md)

<a id="m-epapp-start"></a>
## Agent start path

0. Monorepo factual entry (when unsure which app): [`../../../docs/PROJECT_CONTEXT.md`](../../../docs/PROJECT_CONTEXT.md#m-proj-start)
1. Operational procedures → [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path)
2. Technical design and data flow → [`ARCHITECTURE.md`](ARCHITECTURE.md#m-eparch-flow)
3. Business/reporting intent → [`BUSINESS_CONTEXT.md`](BUSINESS_CONTEXT.md#m-epbiz-reporting)
4. Data path policy → [`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-policy)
5. Outbound lane/source-of-truth model → [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md)

<a id="m-epapp-model"></a>
## Current operating model

- Local-first processing with Python 3.12 + uv ([`pyproject.toml`](../pyproject.toml)).
- Sensitive artifacts and large outputs remain outside git by default ([`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-root), [`.env.example`](../.env.example)).
- Multiple docs are historical snapshots; use status labels before trusting details.
- **Streamlit “Salud de datos”:** Solo lectura sobre el SQLite montado; vigencia crudo vs mart y orígenes `source_file`. [`pipeline/STREAMLIT_DATA_FRESHNESS.md`](pipeline/STREAMLIT_DATA_FRESHNESS.md).
- **Streamlit “Actividad contacto Gmail”:** Lista compacta de correos `gmail:contacto@origenlab.cl` y vínculos a documentos/señales; ver sección Streamlit UI en [`pipeline/BUSINESS_MART.md`](pipeline/BUSINESS_MART.md).
- **Operational trust / publication gate:** Scripts under [`scripts/qa/`](../scripts/qa/) (orchestrated by [`publish_gate.py`](../scripts/qa/publish_gate.py)) compare the client pack snapshot, SQLite lead totals, operational CSVs under [`reports/out/active/`](../reports/out/README.md), and evidence URLs. Logic lives in the [`operational_trust`](../src/origenlab_email_pipeline/operational_trust/) package (facade in [`__init__.py`](../src/origenlab_email_pipeline/operational_trust/__init__.py)). Use this as an automated **consistency** bar before treating lead/client outputs as publish-safe — not as proof of business claims. How to run: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-publish-qa). **Provenance** in `summary.json`, `operational_stack_last_run.json`, per-run `operational_run_manifests/<run_id>.json`, and the scorecard JSON documents `run_id`, `publish_gate` outcome on the manifest, DB paths, and stack flags; the pack explicitly does **not** claim gate validation ([`REPORTING.md`](REPORTING.md#m-eprep-leads-qa)).
- **Cold outreach / marketing export eligibility (Phase 1):** two-lane outbound model with shared gate. **Canonical CLIs:** archive batch [`scripts/leads/build_archive_send_batch.py`](../scripts/leads/build_archive_send_batch.py) (use `--audit-only` for audit-only artifacts); lead queue [`scripts/leads/export_next_marketing_recipients.py`](../scripts/leads/export_next_marketing_recipients.py). Both use [`outbound_core.py`](../src/origenlab_email_pipeline/outbound_core.py) for **aligned** Gmail/Sent defaults and lane-specific `GateContext` construction, then call [`candidate_export_gate.py`](../src/origenlab_email_pipeline/candidate_export_gate.py). Sender/blocker context defaults follow `ORIGENLAB_GMAIL_WORKSPACE_USER` when set. **`Streamlit`** (`apps/business_mart_app.py`): review, RW sidecars, and UI that should call the **same** library paths — **not** the reproducible record of a given export (save CLI CSV/JSON; optional [`print_outbound_run_summary.py`](../scripts/qa/print_outbound_run_summary.py) on summary files). Operator checklist: [`pipeline/OUTBOUND_OPERATOR_CHECKLIST.md`](pipeline/OUTBOUND_OPERATOR_CHECKLIST.md). `contact_master` remains exploratory (not CRM truth). Full policy: [`OUTBOUND_SOURCE_OF_TRUTH.md`](OUTBOUND_SOURCE_OF_TRUTH.md). Read-only sample audit: [`scripts/qa/export_candidate_audit.py`](../scripts/qa/export_candidate_audit.py). Runbook: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-cold-export-gate).
- **Lead script layout:** routine pipeline and outbound CLIs stay in [`scripts/leads/`](../scripts/leads/README.md) (directory root). Supporting exports, hunt tooling, and lead-account maintenance live under [`scripts/leads/advanced/`](../scripts/leads/advanced/README.md). DR50 / ready-8 cohort scripts and versioned JSON are under [`scripts/leads/campaigns/`](../scripts/leads/campaigns/README.md).
- **Python package domains:** the `origenlab_email_pipeline` tree is mostly flat but **commercial intel** has [`commercial/`](../src/origenlab_email_pipeline/commercial/) (root `commercial_intel_*` shims) and **operational trust** is **only** [`operational_trust/`](../src/origenlab_email_pipeline/operational_trust/) (no root `operational_trust_*.py`). Other areas are still grouped by **logical domain** (archive, leads, reports, Streamlit, suppliers, Tatiana, shared core). See [`pipeline/PACKAGE_DOMAINS.md`](pipeline/PACKAGE_DOMAINS.md) for the map, **`lead_*` vs `leads_*`**, import boundaries, and why **`candidate_export_gate`** / **`marketing_export_context`** stay at root for now.
