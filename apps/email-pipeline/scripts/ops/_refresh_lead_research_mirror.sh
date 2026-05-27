#!/usr/bin/env bash
# Opt-in lead_intel.* mirror refresh (SQLite lead_research_* → Postgres lead_intel.*).
# Sourced by refresh_render_dashboard_once.sh when RUN_LEAD_RESEARCH_MIRROR=1.

run_lead_research_mirror_refresh() {
  local pipe_root="${1:?pipe_root required}"
  local verify_json="${2:-/tmp/lead_research_mirror_verify.json}"

  cd "$pipe_root"
  echo ""
  echo "-- Lead research mirror (Phase 10B CSV → SQLite → Postgres lead_intel.*; opt-in) --"
  uv run alembic -c alembic.ini upgrade head
  uv run python scripts/leads/build_lead_research_sqlite.py
  uv run python scripts/sync/sync_lead_research_postgres_mirror.py --dry-run
  uv run python scripts/sync/sync_lead_research_postgres_mirror.py
  if ! uv run python scripts/qa/verify_lead_research_postgres_mirror.py \
    --scan-text \
    --json-out "$verify_json"; then
    echo "Lead research mirror verify failed." >&2
    return 1
  fi
  echo "Lead research mirror verify OK: $verify_json"
  return 0
}
