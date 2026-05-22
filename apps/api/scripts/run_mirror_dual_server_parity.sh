#!/usr/bin/env bash
# API-3 Phase 6: live mirror smoke (disposable Postgres on :5433 only).
# GET-only validation; single apps/api uvicorn on :8001. Legacy :8000 removed.
#
# Usage:
#   ./scripts/run_mirror_dual_server_parity.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
API="$ROOT/apps/api"
PIPE="$ROOT/apps/email-pipeline"
DASH="$ROOT/apps/dashboard"

CONTAINER="${ORIGENLAB_PARITY_PG_CONTAINER:-origenlab-api3-parity-pg}"
PG_URL="${ORIGENLAB_TEST_POSTGRES_URL:-postgresql+psycopg://origenlab:origenlab@127.0.0.1:5433/origenlab_api3_parity_test}"
WORKDIR="${ORIGENLAB_PARITY_WORKDIR:-/tmp/origenlab-api3-parity}"
SQLITE="${WORKDIR}/parity.sqlite"

MIRROR_PID=""

cleanup() {
  [[ -n "${MIRROR_PID}" ]] && kill "${MIRROR_PID}" 2>/dev/null || true
  docker rm -f "${CONTAINER}" 2>/dev/null || true
}
trap cleanup EXIT

if echo "${PG_URL}" | grep -qiE 'origenlab_scratch|/scratch|production|prod'; then
  echo "ERROR: refuse production/scratch Postgres URL for parity run: ${PG_URL}" >&2
  exit 2
fi

rm -rf "${WORKDIR}"
mkdir -p "${WORKDIR}"

echo "== 1. Disposable Postgres (${CONTAINER} on :5433) =="
docker rm -f "${CONTAINER}" 2>/dev/null || true
docker run -d --name "${CONTAINER}" \
  -e POSTGRES_USER=origenlab -e POSTGRES_PASSWORD=origenlab \
  -e POSTGRES_DB=origenlab_api3_parity_test \
  -p 127.0.0.1:5433:5432 postgres:16

for _ in $(seq 1 30); do
  if docker exec "${CONTAINER}" pg_isready -U origenlab -d origenlab_api3_parity_test -q 2>/dev/null; then
    break
  fi
  sleep 1
done
docker exec "${CONTAINER}" pg_isready -U origenlab -d origenlab_api3_parity_test

echo "== 2. Minimal SQLite + Alembic + mirror sync =="
export ORIGENLAB_POSTGRES_URL="${PG_URL}"
export ALEMBIC_DATABASE_URL="${PG_URL}"
export ORIGENLAB_SQLITE_PATH="${SQLITE}"

(cd "${PIPE}" && uv run python - <<'PY'
import sqlite3
from pathlib import Path
import os
from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE
from origenlab_email_pipeline.db import init_schema

db = Path(os.environ["ORIGENLAB_SQLITE_PATH"])
db.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(db)
init_schema(conn)
prefix = CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE.replace("%", "")
conn.execute(
    """INSERT INTO emails (source_file, message_id, date_iso, folder, sender, recipients, subject, body)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (f"{prefix}INBOX/msg", "msg-1", "2026-05-16T10:00:00", "INBOX", "buyer@lab.cl",
     "contacto@origenlab.cl", "Test", "body"),
)
conn.execute("INSERT INTO contact_master (email) VALUES ('buyer@lab.cl')")
conn.execute("INSERT INTO organization_master (domain) VALUES ('lab.cl')")
conn.execute(
    """INSERT INTO opportunity_signals (signal_type, entity_kind, entity_key, created_at)
       VALUES ('test', 'contact', 'buyer@lab.cl', '2026-05-16T10:00:00')"""
)
conn.commit()
conn.close()
print(f"SQLite ready: {db}")
PY
)

(cd "${PIPE}" && uv run alembic upgrade head)

(cd "${PIPE}" && uv run python scripts/sync/sync_dashboard_postgres_mirror.py \
  --sqlite-db "${SQLITE}" \
  --postgres-url "${PG_URL}" \
  --allow-non-scratch-postgres)

echo "== 3. Start mirror API :8001 =="
(cd "${API}" && \
  ORIGENLAB_API_BACKEND=postgres \
  ORIGENLAB_POSTGRES_URL="${PG_URL}" \
  ORIGENLAB_SQLITE_PATH="${SQLITE}" \
  uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8001) &
MIRROR_PID=$!

for _ in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "== 4. Mirror smoke (:8001 only) =="
(cd "${API}" && uv run python scripts/mirror_parity_smoke.py \
  --mirror-base http://127.0.0.1:8001)

echo "== 5. Dashboard mirror smoke (:8001) =="
(cd "${DASH}" && ORIGENLAB_MIRROR_API_BASE_URL=http://127.0.0.1:8001 npm run smoke:mirror)

echo
echo "OK: API-3 mirror live smoke completed (legacy :8000 removed)."
echo "Disposable DB: ${PG_URL}"
echo "Cleanup: container ${CONTAINER} removed on exit."
