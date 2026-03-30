#!/usr/bin/env bash
# One ordered pass: mart → leads normalize/score → lead↔mart matches → account rollup → account↔org matches.
# Uses migrate_sqlite_schema inside the Python entrypoints where adopted (see docs/pipeline/SCHEMA_OWNERSHIP.md).
#
# Usage (from repo root):
#   bash scripts/pipeline/run_aligned_stack.sh
#
# Full mart truncate/rebuild (expensive):
#   FULL_ALIGNED_REBUILD_MART=1 bash scripts/pipeline/run_aligned_stack.sh
#
# Does not run fetch_* ingest; set LEADS_*_FILE and run scripts/leads/run_leads_pipeline.sh or fetch scripts first if needed.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ "${FULL_ALIGNED_REBUILD_MART:-0}" == "1" ]]; then
  echo ">>> Mart build (--rebuild)"
  uv run python scripts/mart/build_business_mart.py --rebuild
else
  echo ">>> Mart build (incremental)"
  uv run python scripts/mart/build_business_mart.py
fi

echo ">>> Normalize leads"
uv run python scripts/leads/normalize_leads.py

echo ">>> Score leads"
uv run python scripts/leads/leads_score.py

echo ">>> Match leads to mart"
uv run python scripts/leads/match_leads_to_mart.py

echo ">>> Lead account rollup"
uv run python scripts/leads/build_lead_account_rollup.py

echo ">>> Match lead accounts to organization_master"
uv run python scripts/leads/match_lead_accounts_to_existing_orgs.py

echo "=== Aligned stack complete ==="
