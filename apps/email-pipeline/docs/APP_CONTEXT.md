# Email Pipeline App Context

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-24

Primary context for [`apps/email-pipeline/`](../).

<a id="m-epapp-purpose"></a>
## Purpose

Transform archived email sources into structured, queryable data and reporting outputs for business analysis and client-facing insights.

<a id="m-epapp-start"></a>
## Agent start path

0. Monorepo factual entry (when unsure which app): [`../../../docs/PROJECT_CONTEXT.md`](../../../docs/PROJECT_CONTEXT.md#m-proj-start)
1. Operational procedures → [`RUNBOOK.md`](RUNBOOK.md#m-eprun-path)
2. Technical design and data flow → [`ARCHITECTURE.md`](ARCHITECTURE.md#m-eparch-flow)
3. Business/reporting intent → [`BUSINESS_CONTEXT.md`](BUSINESS_CONTEXT.md#m-epbiz-reporting)
4. Data path policy → [`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-policy)

<a id="m-epapp-model"></a>
## Current operating model

- Local-first processing with Python 3.12 + uv ([`pyproject.toml`](../pyproject.toml)).
- Sensitive artifacts and large outputs remain outside git by default ([`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-root), [`.env.example`](../.env.example)).
- Multiple docs are historical snapshots; use status labels before trusting details.
- **Operational trust / publication gate:** Scripts under [`scripts/qa/`](../scripts/qa/) (orchestrated by [`publish_gate.py`](../scripts/qa/publish_gate.py)) compare the client pack snapshot, SQLite lead totals, operational CSVs under [`reports/out/active/`](../reports/out/README.md), and evidence URLs. Logic lives in [`operational_trust.py`](../src/origenlab_email_pipeline/operational_trust.py). Use this as an automated **consistency** bar before treating lead/client outputs as publish-safe — not as proof of business claims. How to run: [`RUNBOOK.md`](RUNBOOK.md#m-eprun-publish-qa). **Provenance** in `summary.json`, `operational_stack_last_run.json`, per-run `operational_run_manifests/<run_id>.json`, and the scorecard JSON documents `run_id`, `publish_gate` outcome on the manifest, DB paths, and stack flags; the pack explicitly does **not** claim gate validation ([`REPORTING.md`](REPORTING.md#m-eprep-leads-qa)).
