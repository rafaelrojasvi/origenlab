# Contributing to OrigenLab

This repository is a **monorepo**:

- [`apps/web/`](apps/web/) — Astro marketing site (Node.js).
- [`apps/email-pipeline/`](apps/email-pipeline/) — Python email/leads/reporting pipeline (`uv`, `pytest`, optional ML groups).

Start with the map: [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) and monorepo context: [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md).

## Local setup

### Website (`apps/web`)

- Use Node 20 (see [`apps/web/.nvmrc`](apps/web/.nvmrc)).
- From `apps/web/`: `npm ci`, then `npm run check` and `npm run build` when you change site code.

### Email pipeline (`apps/email-pipeline`)

- Python 3.12 with [`uv`](https://docs.astral.sh/uv/).
- From `apps/email-pipeline/`: `uv sync --group dev --group ui` (matches CI for tests that need Streamlit-related deps).
- Copy [`apps/email-pipeline/.env.example`](apps/email-pipeline/.env.example) to `.env` and point paths at a **directory outside the repo** for real data (see [`apps/email-pipeline/docs/DATA_LOCATIONS.md`](apps/email-pipeline/docs/DATA_LOCATIONS.md)).

## What must not be committed

Do not commit:

- `.env` or any file containing secrets
- PST/mbox archives, SQLite/DB files, JSONL exports, report outputs, caches, virtualenvs, or build artifacts (`dist/`, `.astro/`, `node_modules/`, `.venv/`)

When in doubt, check [`.gitignore`](.gitignore) and the app-level `.gitignore` files.

## Pull requests

Use the repository root PR template ([`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)) and mark which area you touched.

## Security

See [`SECURITY.md`](SECURITY.md) (repo root) and [`apps/email-pipeline/docs/SECURITY.md`](apps/email-pipeline/docs/SECURITY.md) for data-handling expectations.

## Licensing

By contributing, you agree your contributions are licensed under the same terms as this project (see [`LICENSE`](LICENSE)).
