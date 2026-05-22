#!/usr/bin/env bash
# Dashboard/API v1 freeze checklist — SQLite/default only (read-only validation).
#
# Clears stale Postgres env from the caller shell so subprocess tests do not
# hit 127.0.0.1:5437 (or similar) when no disposable DB is running.
#
# Postgres mirror matrix: run separately:
#   ./scripts/run-v1-postgres-matrix-check.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
API="$ROOT/apps/api"
DASH="$ROOT/apps/dashboard"
PIPE="$ROOT/apps/email-pipeline"

# Postgres-related vars must not leak into sqlite/default validation.
for _var in ORIGENLAB_API_BACKEND ORIGENLAB_POSTGRES_URL ORIGENLAB_TEST_POSTGRES_URL ALEMBIC_DATABASE_URL; do
  unset "${_var}" || true
done

echo "== v1 freeze (SQLite/default) =="
echo "Note: Postgres mirror validation is optional — run ./scripts/run-v1-postgres-matrix-check.sh"
echo "      with a live disposable DB (not production/scratch Postgres)."
if [[ -n "${ORIGENLAB_SQLITE_PATH:-}" ]]; then
  echo "Using ORIGENLAB_SQLITE_PATH=${ORIGENLAB_SQLITE_PATH}"
else
  echo "ORIGENLAB_SQLITE_PATH not set (apps/api tests use their own fixtures)."
fi
echo

run_clean() {
  env -u ORIGENLAB_API_BACKEND -u ORIGENLAB_POSTGRES_URL -u ORIGENLAB_TEST_POSTGRES_URL -u ALEMBIC_DATABASE_URL "$@"
}

echo "== apps/api pytest =="
run_clean bash -c "cd \"$API\" && uv run pytest tests -q"

echo "== apps/dashboard npm test =="
run_clean bash -c "cd \"$DASH\" && npm test"

echo "== apps/dashboard production build =="
run_clean bash -c "cd \"$DASH\" && VITE_ORIGENLAB_API_BASE_URL=https://api.example.com npm run build"

echo "== apps/api sqlite smoke =="
run_clean bash -c "cd \"$API\" && uv run python scripts/dashboard_v1_http_smoke.py --expect-backend sqlite"

echo "== apps/email-pipeline mirror unit tests (no live Postgres) =="
run_clean bash -c "cd \"$PIPE\" && uv run pytest \
  tests/test_sync_dashboard_postgres_mirror.py \
  tests/test_load_equipment_opportunity_mirror.py \
  tests/test_warm_case_promotion.py \
  tests/test_db1_preflight_static.py -q \
  -m 'not integration'"

echo
echo "OK: v1 SQLite freeze checklist passed."
