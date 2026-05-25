# Shared cloud Postgres env setup for ops shell scripts.
# Usage: cloud_postgres_prepare_env "$PIPE_ROOT"
# Requires: ORIGENLAB_CLOUD_POSTGRES_URL (unchanged on success)
# Sets: ORIGENLAB_POSTGRES_URL, ALEMBIC_DATABASE_URL (psycopg driver, same credentials)
# Prints: HOST_DB via caller (from HOST_DB variable after eval)

cloud_postgres_prepare_env() {
  local pipe_root="${1:?pipe_root required}"
  if [[ -z "${ORIGENLAB_CLOUD_POSTGRES_URL:-}" ]]; then
    echo "ERROR: ORIGENLAB_CLOUD_POSTGRES_URL is not set." >&2
    return 2
  fi

  local out
  if ! out="$(
    cd "$pipe_root" && uv run python scripts/ops/cloud_postgres_url.py prepare 2>&1
  )"; then
    echo "$out" >&2
    return 2
  fi

  # shellcheck disable=SC1090
  eval "$out"
  export ORIGENLAB_POSTGRES_URL="${NORMALIZED_URL}"
  export ALEMBIC_DATABASE_URL="${NORMALIZED_URL}"
}
