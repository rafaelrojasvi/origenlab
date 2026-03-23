# OrigenLab — Repository Agent Instructions

## Project overview

This file is a **policy overlay** for the web app workspace. Factual truth lives in monorepo + app docs and in code.

## Instruction precedence

**Factual project truth** (must not be overridden by this file):

1. Monorepo: [`../../docs/PROJECT_CONTEXT.md`](../../docs/PROJECT_CONTEXT.md#m-proj-precedence) *(from `apps/web/` → repo root)*
2. Web: [`docs/APP_CONTEXT.md`](docs/APP_CONTEXT.md#m-web-agent-start), [`docs/BUSINESS_CONTEXT.md`](docs/BUSINESS_CONTEXT.md#m-webbiz-objective), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#m-webarch-stack), [`docs/RUNBOOK.md`](docs/RUNBOOK.md#m-webrun-local), and other canonical web docs under [`docs/`](docs/)
3. Web app [`README.md`](README.md)
4. [`src/data/`](src/data/) and the rest of the repo (code, configs)

**Policy and workflow** (this file and tooling):

5. [`AGENTS.md`](AGENTS.md) (this file) — non‑negotiable content/safety rules
6. [`.cursor/rules/`](.cursor/rules/)
7. [`.claude/agents/`](.claude/agents/)
8. [`.claude/skills/`](.claude/skills/)

If a policy line here **contradicts** a fact in [`PROJECT_CONTEXT.md`](../../docs/PROJECT_CONTEXT.md#m-proj-precedence), app canonical docs, or `src/data/*`, **follow the factual doc or data** and treat the policy as needing an update—not as permission to invent facts.

Rules, agents, and skills should reference canonical sources instead of duplicating volatile facts.

## Canonical context docs (read first)

- [`docs/APP_CONTEXT.md`](docs/APP_CONTEXT.md)
- [`docs/BUSINESS_CONTEXT.md`](docs/BUSINESS_CONTEXT.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md#m-webrun-local)
- Data truth: [`src/data/`](src/data/)

## Quick checks

- Use [`src/data/`](src/data/) as factual source of truth.
- If deployment-related, use [`docs/RUNBOOK.md`](docs/RUNBOOK.md#m-webrun-deploy) then [`docs/deployment.md`](docs/deployment.md).
- Do not invent brands, certifications, specs, delivery times, warranty terms, or partnerships.

## Non-negotiable content rules

Do not invent:
- brands
- certifications
- official partnerships
- technical specifications
- product availability
- warranty terms beyond what is explicitly provided
- installation coverage details not confirmed in the repo
- response time promises
- client logos or customer names
- regulatory claims

If information is missing, use placeholders in code/comments or write copy that stays general and truthful.

## When editing or generating content

Always optimize for:
1. factual correctness
2. clarity
3. maintainability
4. commercial usefulness
5. easy quotation/contact flow

If asked to create new copy and information is incomplete, write the safest truthful version.
