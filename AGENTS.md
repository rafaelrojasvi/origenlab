# OrigenLab monorepo — agent instructions

## Scope

This file applies to the **whole monorepo**. For **email-pipeline** work, read **[`apps/email-pipeline/AGENTS.md`](apps/email-pipeline/AGENTS.md)** first — it has stricter safety rules and the operator reading list.

For **public website** work, read **[`apps/web/AGENTS.md`](apps/web/AGENTS.md)**.

## Factual entry

1. [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — what each app is
2. App-specific `docs/APP_CONTEXT.md` and `docs/RUNBOOK.md`

## Hard rules (all apps)

- Do not invent business facts (brands, specs, certifications, client names).
- Do not delete files unless the user explicitly requests it.
- Do not run destructive git operations without explicit approval.
- Prefer read-only investigation before mutating production data.

## Email-pipeline reminder

Outbound and archive work lives under **`apps/email-pipeline/`**. Agents must **not** send email, mutate Gmail, or run Postgres migrations without explicit user approval. Read **`apps/email-pipeline/docs/EXPERIMENTAL_PARKED.md`** before Postgres/API/Tatiana/ML work; do not use **LEGACY_DO_NOT_USE** scripts for current operator tasks. Start with **`operator_status.py`** and **`reports/out/active/current/manifest.json`** when checking operational state.
