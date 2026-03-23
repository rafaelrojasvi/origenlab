# Skill: astro-hostgator-deploy

## Purpose

Use this skill whenever preparing, checking, or documenting deployment for the OrigenLab Astro site on static/shared hosting.

## When to use

Use this skill for:
- pre-deploy review
- build verification
- static hosting checks
- HostGator upload guidance
- troubleshooting incorrect production uploads
- checking for path/output mistakes

## Assumptions

Default assumptions:
- Astro site
- static output
- build artifacts in `dist/`
- deployment to shared hosting
- no server runtime available in production unless explicitly documented

Canonical deployment authority: `docs/deployment.md` and `docs/deployment-status.md`.

## Main risks to catch

Watch for:
- build not run before upload
- wrong folder uploaded
- nested `dist/dist`
- broken asset paths
- stale files on hosting
- assumptions that require Node/server execution
- incorrect base path config

## Workflow

When using this skill:
1. inspect package scripts
2. confirm build command
3. confirm output directory
4. verify static compatibility
5. note anything that would fail on shared hosting
6. provide the smallest correct deployment instructions

## Expected checks

Check whether:
- `npm run check` exists and should be run
- `npm run build` succeeds
- output goes to `dist/`
- assets resolve correctly
- public files are included correctly
- deployment instructions mention uploading the correct contents

## Output format

Return:
1. deployment readiness summary
2. issues found
3. exact deployment steps
4. rollback or troubleshooting notes if needed

## Safe deployment guidance pattern

Typical safe deployment flow:
- install deps
- run checks
- run build
- inspect `dist/`
- upload correct build output to hosting root / `public_html`
- verify live assets and navigation

## Important constraint

Do not assume backend features, server routes, or runtime environment support unless the repo clearly includes and documents them.
