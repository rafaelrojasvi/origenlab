#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Render-style runtime install: catch missing runtime deps (e.g. psycopg) before deploy.
uv sync --frozen --no-dev
uv run --no-sync python - <<'PY'
import psycopg
import origenlab_api.main
print("ok: apps/api no-dev runtime imports")
PY

uv sync --group dev --frozen
ORIGENLAB_API_BACKEND=sqlite \
ORIGENLAB_POSTGRES_URL= \
ALEMBIC_DATABASE_URL= \
uv run --frozen pytest tests -q
