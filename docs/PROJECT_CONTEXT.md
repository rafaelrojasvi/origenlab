# Project Context

Status: canonical  
Owner: project-maintainers  
Last reviewed: 2026-03-24

This is the primary monorepo context document for coding agents and contributors.

<a id="m-proj-what"></a>
## What this repo is

OrigenLab monorepo with two active applications:

- [`apps/web`](../apps/web/): public marketing website (Astro, static deployment).
- [`apps/email-pipeline`](../apps/email-pipeline/): email archive ingestion, enrichment, and reporting pipeline (Python + uv).

<a id="m-proj-business"></a>
## Business goal

Support OrigenLab's commercial operation by:

- presenting clear, trustworthy public website content for quotation flows.
- extracting business signal from historical email archives into operational reports.

<a id="m-proj-start"></a>
## Where to start (agent-first)

1. Read this file.
2. Choose app domain:
   - Web → [apps/web/docs/APP_CONTEXT.md](../apps/web/docs/APP_CONTEXT.md)
   - Email pipeline → [apps/email-pipeline/docs/APP_CONTEXT.md](../apps/email-pipeline/docs/APP_CONTEXT.md)
3. Open only the canonical doc for your task type (under that app’s `docs/`, e.g. [apps/web/docs/RUNBOOK.md](../apps/web/docs/RUNBOOK.md#m-webrun-local) or [apps/email-pipeline/docs/RUNBOOK.md](../apps/email-pipeline/docs/RUNBOOK.md#m-eprun-path)):
   - run/procedure → `RUNBOOK.md` (in that app’s `docs/`)
   - architecture/data flow → `ARCHITECTURE.md`
   - business/scope constraints → `BUSINESS_CONTEXT.md`

<a id="m-proj-rules"></a>
## Canonical source rules

- Business facts should come from canonical app data/docs, not duplicated agent overlays.
- Run procedures should come from app runbooks.
- Historical docs are reference-only.

<a id="m-proj-precedence"></a>
## Precedence

**Factual project truth** (what the repo is, how it runs, where data lives):

1. This file ([`docs/PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md))
2. That app’s [`APP_CONTEXT.md`](../apps/web/docs/APP_CONTEXT.md) (web) or [`APP_CONTEXT.md`](../apps/email-pipeline/docs/APP_CONTEXT.md) (email-pipeline), plus other **canonical app docs** in the same `docs/` folder (`RUNBOOK.md`, `ARCHITECTURE.md`, `BUSINESS_CONTEXT.md`; email-pipeline also [`DATA_LOCATIONS.md`](../apps/email-pipeline/docs/DATA_LOCATIONS.md#m-epdata-root)), and domain subfolders as in [`DOCUMENTATION_MAP.md`](./DOCUMENTATION_MAP.md#m-docmap-mapping)
3. That app’s [`README.md`](../apps/web/README.md) (web) or [`README.md`](../apps/email-pipeline/README.md) (email-pipeline)
4. Executable source: code, scripts, [`apps/email-pipeline/pyproject.toml`](../apps/email-pipeline/pyproject.toml) / [`apps/web/package.json`](../apps/web/package.json), schema modules, [`apps/email-pipeline/.env.example`](../apps/email-pipeline/.env.example)

**Policy and agent behavior** (safety rules, tone, “do not invent”, editor overlays):

- [`apps/web/AGENTS.md`](../apps/web/AGENTS.md), [`.cursor/rules`](../apps/web/.cursor/rules), [`.claude/agents`](../apps/web/.claude/agents), [`.claude/skills`](../apps/web/.claude/skills) — **must not override** factual statements in the layers above. If policy and facts conflict, **facts win**; adjust policy or the doc, do not invent implementation.

**Last:**

5. Historical, archive, and generated snapshots (`Status: historical` / [`generated/`](../apps/email-pipeline/docs/generated/) / dated audits)

<a id="m-proj-trust"></a>
## What not to trust as current truth

- Dated audits, one-off plans, and machine snapshots.
- Any doc explicitly marked `Status: historical` or `Status: generated` without recent regeneration.

<a id="m-proj-nav"></a>
## Navigation

- Documentation map: [`DOCUMENTATION_MAP.md`](./DOCUMENTATION_MAP.md#m-docmap-entry) · [link check & linking conventions](./DOCUMENTATION_MAP.md#m-docmap-link-check)
- Historical monorepo migration notes: [`MONOREPO.md`](./MONOREPO.md)
