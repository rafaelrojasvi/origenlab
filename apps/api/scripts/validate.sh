#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv sync --group dev --frozen
ORIGENLAB_API_BACKEND=sqlite \
ORIGENLAB_POSTGRES_URL= \
ALEMBIC_DATABASE_URL= \
uv run --frozen pytest tests -q
