#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv sync --group dev --frozen
uv run pytest tests -q
