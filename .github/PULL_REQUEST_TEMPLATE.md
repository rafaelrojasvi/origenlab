## Summary

<!-- What changed and why (English or Spanish is fine) -->

## Scope

- [ ] `apps/web` (Astro site)
- [ ] `apps/email-pipeline` (Python / uv)
- [ ] Root / shared (CI, docs, tooling)

## Checklist

### Web (`apps/web`)

- [ ] `npm run check` passes (if you changed site code)
- [ ] `npm run build` passes (if you changed site code)
- [ ] Business/contact facts live in `apps/web/src/data/*` (not hardcoded in pages)
- [ ] If you changed public copy: tone and claims align with `apps/web/docs/company-scope.md` / `AGENTS.md`

### Email pipeline (`apps/email-pipeline`)

- [ ] `uv run pytest` passes (if you changed pipeline code)
- [ ] No secrets, archives, databases, JSONL exports, or sensitive reports committed (see repo and app `.gitignore`)

## Notes / screenshots

<!-- Optional -->
