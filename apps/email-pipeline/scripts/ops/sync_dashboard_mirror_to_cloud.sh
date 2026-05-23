#!/usr/bin/env bash
# Manual SQLite → cloud Postgres dashboard mirror (Phase 1).
# SAFETY: Read-only SQLite; writes cloud Postgres mirror only. No Gmail ingest, no mart rebuild.
set -euo pipefail

PIPE="$(cd "$(dirname "$0")/../.." && pwd)"

: "${ORIGENLAB_SQLITE_PATH:?Set ORIGENLAB_SQLITE_PATH to local canonical SQLite (not uploaded)}"
: "${ORIGENLAB_CLOUD_POSTGRES_URL:?Set ORIGENLAB_CLOUD_POSTGRES_URL to cloud external Postgres URL}"

if [[ "${ORIGENLAB_CLOUD_POSTGRES_URL}" == *"@127.0.0.1"* ]] || [[ "${ORIGENLAB_CLOUD_POSTGRES_URL}" == *"localhost"* ]]; then
  echo "ERROR: ORIGENLAB_CLOUD_POSTGRES_URL looks local — use cloud external URL." >&2
  exit 2
fi

export ORIGENLAB_POSTGRES_URL="${ORIGENLAB_CLOUD_POSTGRES_URL}"
export ALEMBIC_DATABASE_URL="${ORIGENLAB_CLOUD_POSTGRES_URL}"

cd "$PIPE"
uv sync --group dev >/dev/null

echo "== Phase 1 cloud mirror sync =="
echo "SQLite: ${ORIGENLAB_SQLITE_PATH}"
echo "Postgres: $(echo "${ORIGENLAB_CLOUD_POSTGRES_URL}" | sed -E 's#://([^:]+):)[^@]+@#://\1:***@#')"

uv run alembic -c alembic.ini upgrade head

uv run python scripts/sync/sync_dashboard_postgres_mirror.py \
  --allow-non-scratch-postgres \
  --include-equipment-opportunities \
  --include-warm-cases \
  --updated-by "${ORIGENLAB_SYNC_UPDATED_BY:-phase1-cloud-manual}" \
  --reason "${ORIGENLAB_SYNC_REASON:-Phase 1 cloud dashboard mirror manual sync}" \
  --json-out /tmp/phase1_cloud_mirror_sync.json

uv run python scripts/qa/verify_dashboard_postgres_mirror.py --json-out /tmp/phase1_cloud_mirror_verify.json

echo "Sync JSON: /tmp/phase1_cloud_mirror_sync.json"
echo "Verify JSON: /tmp/phase1_cloud_mirror_verify.json"
