#!/usr/bin/env bash
# Outbound sidecar mirror refresh (read-only SQLite → Postgres outbound.*).
# Sourced by refresh_render_dashboard_once.sh when RUN_OUTBOUND_SIDECAR_MIRROR=1.

run_outbound_sidecar_mirror_refresh() {
  local pipe_root="${1:?pipe_root required}"
  local verify_json="${2:-/tmp/outbound_sidecar_mirror_verify.json}"
  local include_lead="${3:-0}"

  cd "$pipe_root"
  echo ""
  echo "-- Outbound sidecar mirror → Render Postgres (suppression + outreach state) --"
  uv run python scripts/migrate/sqlite_outbound_sidecars_to_postgres.py --replace

  local verify_args=(--json-out "$verify_json")
  if [[ "$include_lead" == "1" ]]; then
    verify_args+=(--include-lead-research)
  fi

  if ! uv run python scripts/qa/verify_outbound_sidecar_postgres_mirror.py "${verify_args[@]}"; then
    echo "Outbound sidecar mirror verify failed. Dashboard may show PRECAUCIÓN / stale suppressions." >&2
    return 1
  fi
  echo "Outbound sidecar mirror verify OK: $verify_json"
  return 0
}
