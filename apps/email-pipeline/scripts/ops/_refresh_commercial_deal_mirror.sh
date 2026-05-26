#!/usr/bin/env bash
# Opt-in commercial.deal mirror refresh (read-only SQLite → Postgres commercial.deal).
# Sourced by refresh_render_dashboard_once.sh when RUN_COMMERCIAL_DEAL_MIRROR=1.

run_commercial_deal_mirror_refresh() {
  local pipe_root="${1:?pipe_root required}"
  local verify_json="${2:-/tmp/commercial_deals_mirror_verify.json}"

  cd "$pipe_root"
  echo ""
  echo "-- Commercial deal mirror → Render Postgres (opt-in) --"
  uv run python scripts/sync/sync_commercial_deals_postgres_mirror.py --dry-run
  uv run python scripts/sync/sync_commercial_deals_postgres_mirror.py
  if ! uv run python scripts/qa/verify_commercial_deals_postgres_mirror.py \
    --scan-jsonb \
    --json-out "$verify_json"; then
    echo "Commercial deal mirror verify failed. Dashboard normal mirror may still be fresh, but commercial deal data should not be trusted." >&2
    return 1
  fi
  return 0
}
