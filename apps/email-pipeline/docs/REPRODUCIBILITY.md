# Reproducibility (email-pipeline)

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-04-25

## Purpose

Describe how to **reproduce the development and test environment** for `apps/email-pipeline` on a new machine, and which parts of **real operations** are **not** in git.

## What you can reproduce from git alone

- All **Python source** and **scripts**
- **Tests** (with `uv` and the dev dependency group)
- **Dependency lock** behavior via `uv sync` (using `pyproject.toml` + `uv.lock`)
- **Documentation** (including operator maps and safety notes)
- A **read-only sanity check** of the environment: [`scripts/qa/check_reproducibility.py`](../scripts/qa/check_reproducibility.py)

**A new machine can reproduce code and tests from git, but cannot reproduce production operations without the private DB and Gmail credentials.**

## What you cannot reproduce from git alone

- A **production or operational SQLite database** (paths are gitignored; data stays outside the repo)
- **Gmail OAuth** client and refresh token files
- **Secrets** in `.env` (file is gitignored; use `.env.example` as a template)
- **Historical** `reports/out/*` (mostly gitignored; see `reports/out/README.md`)
- **Optional** remote services: Postgres (migration/audit), OpenAI (Tatiana / optional tooling)

## External / private files (typical)

| Item | Role |
|------|------|
| **Production / operational SQLite DB** | Runtime source of truth for email archive, marts, leads, outbound state |
| **Gmail OAuth client JSON** | `ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON` (Desktop app credentials from Google Cloud) |
| **Gmail OAuth token JSON** | `ORIGENLAB_GMAIL_TOKEN_JSON` (refresh token; created on first OAuth flow) |
| **`.env`** | Local `ORIGENLAB_*` paths and feature flags; never commit |
| **OpenAI / API keys** (optional) | `ORIGENLAB_TATIANA_OPENAI_*` or `OPENAI_API_KEY` for copilot / eval |
| **Postgres URL** (optional) | `ORIGENLAB_POSTGRES_URL` / `ALEMBIC_DATABASE_URL` for migrations and optional audit |

## Setup commands

From the monorepo (paths relative to `apps/email-pipeline/` where commands run):

```bash
cd apps/email-pipeline
uv python install 3.12
uv sync
```

Optional **dependency groups** (install what you use):

```bash
uv sync --group workspace   # Google OAuth for Gmail IMAP / API tooling
uv sync --group ui          # Streamlit / pandas stack
uv sync --group postgres    # Alembic + drivers
uv sync --group ml          # torch / embeddings (CUDA index in pyproject)
```

Copy env template and edit (paths, secrets):

```bash
cp .env.example .env
```

## Test command

```bash
uv run pytest tests -q
```

## Readiness and ingest (operational, not required for tests)

- **Outbound readiness (read-only):**  
  `uv run python scripts/qa/check_outbound_readiness.py`
- **Environment + docs + DB presence (read-only, no network):**  
  `uv run python scripts/qa/check_reproducibility.py`
- **List Gmail IMAP folder labels (requires OAuth; network):**  
  `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --list-folders`
- **Ingest Sent (requires OAuth; network; writes DB):**  
  `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --folder "[Gmail]/Enviados"`

## Daily outbound lanes

Do not duplicate the full runbooks here. Use **[`SCRIPT_MAP.md`](SCRIPT_MAP.md)** and [`RUNBOOK.md`](RUNBOOK.md) for the volume and precision lanes, post-send steps, and break-glass tools.

## Related

- **Mutation policy:** [`CRUD_SAFETY.md`](CRUD_SAFETY.md)  
- **Script grouping (inventory):** [`SCRIPT_INVENTORY.md`](SCRIPT_INVENTORY.md)  
- **Operator map:** [`SCRIPT_MAP.md`](SCRIPT_MAP.md)
