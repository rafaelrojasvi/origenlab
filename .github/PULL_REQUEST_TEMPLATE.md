## Summary

<!-- What changed and why (English or Spanish is fine) -->

## Scope

- [ ] `apps/web` — Astro marketing site
- [ ] `apps/email-pipeline` — Python / SQLite / Gmail / operator pipeline
- [ ] `apps/api` — FastAPI read-only operator API
- [ ] `apps/dashboard` — React operator dashboard
- [ ] Root/shared — CI, docs, tooling, repo config

## Checklist

### Web (`apps/web`)

- [ ] `cd apps/web && npm ci`
- [ ] `npm run check`
- [ ] `npm run validate:catalog`
- [ ] `npm run build`
- [ ] Business/contact facts live in `apps/web/src/data/*` (not hardcoded in pages)
- [ ] If you changed public copy: tone and claims align with `apps/web/docs/company-scope.md` / `AGENTS.md`

### Email pipeline (`apps/email-pipeline`)

- [ ] `cd apps/email-pipeline`
- [ ] `uv sync --group dev --group ui --group postgres --group lab --frozen`
- [ ] `uv run pytest tests -q`
- [ ] `uv run origenlab refresh-dashboard` for plan-only operator check when relevant
- [ ] No Gmail/Postgres/send/purge/`--apply` unless explicitly intended and documented
- [ ] No secrets, archives, databases, JSONL exports, or sensitive reports committed (see repo and app `.gitignore`)

### API (`apps/api`)

- [ ] `cd apps/api`
- [ ] `uv sync --group dev --frozen`
- [ ] `uv run pytest tests -q`
- [ ] API remains GET-only/read-only
- [ ] No Gmail ingest, send, migration, mirror sync, or outreach-state write imports added
- [ ] Contract tests updated if response fields changed

### Dashboard (`apps/dashboard`)

- [ ] `cd apps/dashboard`
- [ ] `npm ci`
- [ ] `npm test`
- [ ] `npm run build`
- [ ] No mutating HTTP methods added
- [ ] No forbidden DB/pipeline imports added
- [ ] Smoke command run if API-facing behavior changed

### Root/shared

- [ ] Relevant workflow/docs checked
- [ ] Path filters updated if app boundaries changed
- [ ] Lockfiles only changed intentionally

## Verification / risks

<!-- What you ran, what you did not run, and any rollout or safety notes -->

## Notes / screenshots

<!-- Optional -->
