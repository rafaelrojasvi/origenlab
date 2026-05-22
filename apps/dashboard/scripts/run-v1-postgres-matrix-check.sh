#!/usr/bin/env bash
# Optional Dashboard v1 Postgres mirror matrix validation.
#
# Requires a LIVE DISPOSABLE Postgres (e.g. docker on :5433). Do NOT use
# production or shared origenlab_scratch unless you explicitly accept that risk.
#
# Prereqs: alembic upgrade head + sync_dashboard_postgres_mirror.py on disposable DB.
# See docs/V1_FREEZE_OPERATOR_HANDOFF.md Mode 2.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
API="$ROOT/apps/api"
DASH="$ROOT/apps/dashboard"
PIPE="$ROOT/apps/email-pipeline"

PG_URL="${ORIGENLAB_TEST_POSTGRES_URL:-${ORIGENLAB_POSTGRES_URL:-}}"

if [[ -z "${PG_URL}" ]]; then
  echo "ERROR: Postgres matrix check requires a disposable database URL." >&2
  echo "  Set ORIGENLAB_TEST_POSTGRES_URL (preferred) or ORIGENLAB_POSTGRES_URL." >&2
  echo "  Example: postgresql://user:pass@127.0.0.1:5433/origenlab_matrix_test" >&2
  echo "  Do NOT use production/scratch Postgres for this script." >&2
  exit 2
fi

if echo "${PG_URL}" | grep -qiE 'scratch|prod|production'; then
  echo "ERROR: URL looks like production/scratch Postgres. Use a disposable test instance only." >&2
  exit 2
fi

echo "== v1 Postgres mirror matrix (disposable DB only) =="
echo "Using: $(echo "${PG_URL}" | sed -E 's#://([^:]+):)[^@]+@#://\1***@#')"

export ORIGENLAB_POSTGRES_URL="${PG_URL}"
export ORIGENLAB_TEST_POSTGRES_URL="${PG_URL}"
export ORIGENLAB_API_BACKEND=postgres

echo "== connectivity probe =="
(cd "$PIPE" && uv run python - <<'PY'
import os
import sys

url = os.environ.get("ORIGENLAB_TEST_POSTGRES_URL") or os.environ.get("ORIGENLAB_POSTGRES_URL")
if not url:
    print("ERROR: missing Postgres URL", file=sys.stderr)
    sys.exit(2)
try:
    import psycopg
except ImportError:
    print("ERROR: psycopg not installed (uv sync --group postgres in apps/email-pipeline)", file=sys.stderr)
    sys.exit(2)
try:
    with psycopg.connect(url, connect_timeout=5) as conn:
        conn.execute("SELECT 1")
except Exception as exc:
    print(f"ERROR: cannot reach disposable Postgres: {exc}", file=sys.stderr)
    print("Start Docker Postgres on the configured host/port, then retry.", file=sys.stderr)
    sys.exit(2)
print("Postgres connectivity: OK")
PY
)

echo "== apps/api postgres smoke =="
(cd "$API" && uv run python scripts/dashboard_v1_http_smoke.py --expect-backend postgres)

echo "== apps/dashboard postgres smoke (API on :8001 required) =="
(cd "$DASH" && EXPECT_BACKEND=postgres npm run smoke:postgres) || {
  echo "WARN: dashboard HTTP smoke failed (is apps/api running with postgres backend on :8001?)" >&2
  exit 1
}

echo "== apps/api postgres integration tests (optional subset) =="
(cd "$API" && uv run pytest tests/test_postgres_warm_cases.py tests/test_postgres_equipment.py -q -k integration) || true

echo "== apps/email-pipeline postgres integration tests =="
(cd "$PIPE" && uv run pytest \
  tests/test_load_equipment_opportunity_mirror.py \
  tests/test_sync_dashboard_postgres_mirror.py -q -m integration) || true

echo
echo "OK: Postgres matrix check finished (review integration skips/failures above)."
