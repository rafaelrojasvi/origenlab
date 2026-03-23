# Monorepo migration notes

Status: historical  
Owner: project-maintainers  
Last reviewed: 2026-03-23

## What changed

- **`apps/web/`** — Full history from `git@github.com:rafaelRojasVi/origenlab-web.git` (default branch `main`) was added with `git subtree add --prefix=apps/web`.
- **`apps/email-pipeline/`** — The former standalone `origenlab-email-pipeline` project; run all commands from that directory (see its README).

## Deprecate the old website remote

On GitHub, for **origenlab-web**:

1. Settings → **Archive this repository** (recommended), **or**
2. Add a short **README** at the top stating the canonical repo is the monorepo and linking to it.

No need to delete the old repo; archiving preserves stars, issues, and links.

## Pulling subtree updates (optional)

If you still push hotfixes to `origenlab-web` before fully switching:

```bash
git fetch web
git subtree pull --prefix=apps/web web main
```

After migration, prefer committing directly on the monorepo and remove the `web` remote when you no longer need it.
