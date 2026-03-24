# OrigenLab

Monorepo for OrigenLab engineering: **marketing site** (Astro) and **email / lead pipeline** (Python).

| App | Path | Stack |
|-----|------|--------|
| Website | [`apps/web/`](apps/web/) | Astro 5, Tailwind 4, Node 20 (see [`apps/web/.nvmrc`](apps/web/.nvmrc)) |
| Email pipeline | [`apps/email-pipeline/`](apps/email-pipeline/) | Python 3.12, uv, optional CUDA ML — see that app’s [README](apps/email-pipeline/README.md) |

## Documentation hubs

- Agent-first monorepo context: [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md#m-proj-start)
- Monorepo map: [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md#m-docmap-entry)
- Quote & supplier business rules (canonical): [`docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md)
- Web app docs: [`apps/web/docs/README.md`](apps/web/docs/README.md)
- Email pipeline docs: [`apps/email-pipeline/docs/README.md`](apps/email-pipeline/docs/README.md)

## Quick start

**Website**

```bash
cd apps/web
npm ci
npm run build
```

**Email pipeline**

```bash
cd apps/email-pipeline
uv sync --group dev --group ui
uv run pytest
```

(`--group ui` is required for Streamlit-related tests in CI. Default `uv sync` (no extra groups) installs **base** email-pipeline dependencies only—**not** the ML stack; use `uv sync --group ml` for embeddings/CUDA tooling. CI for this app uses `--group dev` + `--group ui`.)

## CI

GitHub Actions workflows are path-filtered under [`.github/workflows/`](.github/workflows/): changes under `apps/web/` run the web build; changes under `apps/email-pipeline/` run Python tests.

## New remote

After you create an empty GitHub repository for this monorepo:

```bash
cd /path/to/this/clone
git remote add origin git@github.com:YOUR_USER/YOUR_MONOREPO.git
git push -u origin main
```

## Legacy `origenlab-web` repository

The site history was imported into `apps/web/` with **`git subtree`**. The standalone repo [`origenlab-web`](https://github.com/rafaelRojasVi/origenlab-web) should be **archived** (or given a README redirect) so work continues only here. See [docs/MONOREPO.md](docs/MONOREPO.md).
