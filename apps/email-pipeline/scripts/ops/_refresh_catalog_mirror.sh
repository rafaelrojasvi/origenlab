#!/usr/bin/env bash
# Opt-in catalog.* mirror refresh (SQLite catalog_* → Postgres catalog.*).
# Sourced by refresh_render_dashboard_once.sh when RUN_CATALOG_MIRROR=1.

_print_catalog_counts_from_verify() {
  local verify_json="${1:?verify_json required}"
  if [[ ! -f "$verify_json" ]]; then
    return 0
  fi
  uv run python -c "
import json, sys
payload = json.load(open(sys.argv[1]))
counts = payload.get('postgres_counts') or {}
for key in ('products', 'supplier_offers', 'price_snapshots', 'commercial_history'):
    print(f'  {key}: {counts.get(key, \"—\")}')
" "$verify_json"
}

run_catalog_mirror_refresh() {
  local pipe_root="${1:?pipe_root required}"
  local verify_json="${2:-/tmp/catalog_postgres_mirror_verify.json}"

  cd "$pipe_root"
  echo ""
  echo "-- Catalog mirror (SQLite catalog_* → Render Postgres; opt-in) --"
  uv run alembic -c alembic.ini upgrade head
  uv run python scripts/catalog/build_catalog_sqlite.py
  uv run python scripts/sync/sync_catalog_postgres_mirror.py --dry-run
  uv run python scripts/sync/sync_catalog_postgres_mirror.py
  if ! uv run python scripts/qa/verify_catalog_postgres_mirror.py \
    --scan-text \
    --json-out "$verify_json"; then
    echo "Catalog mirror verify failed. Dashboard mirror may still be fresh, but Catálogo / catalog API data should not be trusted." >&2
    return 1
  fi
  echo "Catalog mirror verify OK: $verify_json"
  echo "Postgres catalog counts:"
  _print_catalog_counts_from_verify "$verify_json"
  return 0
}
