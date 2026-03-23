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
