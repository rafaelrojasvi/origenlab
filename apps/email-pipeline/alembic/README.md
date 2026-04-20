# Alembic (PostgreSQL target)

Migrations apply to **PostgreSQL only**. The operational app continues to use **SQLite**; no application code reads these tables yet.

## Setup

```bash
cd apps/email-pipeline
uv sync --group postgres
```

Set a database URL (**required** for `upgrade` / `current` / etc.). First match wins:

1. `ALEMBIC_DATABASE_URL`
2. `ORIGENLAB_POSTGRES_URL`

```bash
export ALEMBIC_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/origenlab_email_pg"
# or:
export ORIGENLAB_POSTGRES_URL="postgresql+psycopg://user:password@localhost:5432/origenlab_email_pg"
```

## Commands

```bash
# Show current head
uv run alembic current

# Upgrade to latest
uv run alembic upgrade head

# Downgrade one step (if revisions exist)
uv run alembic downgrade -1
```

If neither variable is set, Alembic exits with an error explaining that Postgres migrations need a URL (SQLite is not used).

Design reference: `docs/pipeline/POSTGRES_SCHEMA_TARGET_V1.md`.
