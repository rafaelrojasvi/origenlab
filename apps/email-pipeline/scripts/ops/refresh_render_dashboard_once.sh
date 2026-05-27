#!/usr/bin/env bash
# Manual one-shot refresh: local SQLite → Render Postgres dashboard mirror.
#
# SAFETY (default):
#   - No Gmail sends; ingest is read-only IMAP (optional, off by default).
#   - No Gmail mutation (no --replace-source).
#   - No outreach-state writes; no refresh_outbound_safety_memory.
#   - No build_business_mart.py --rebuild (incremental mart only).
#   - No build_commercial_intel_v1.py --rebuild (incremental commercial only).
#   - No SQLite backup; no destructive SQL; no dashboard/API writes.
#   - No commercial ledger writes (deal mirror reads SQLite only).
#
# Required env:
#   ORIGENLAB_SQLITE_PATH          local canonical SQLite (read in place)
#   ORIGENLAB_CLOUD_POSTGRES_URL   Render external Postgres URL
#
# Optional env:
#   RUN_GMAIL_INGEST=1             run Gmail ingest before sync (default 0)
#   RUN_COMMERCIAL_DEAL_MIRROR=1   sync+verify commercial.deal after dashboard mirror (default 0)
#   DASHBOARD_FAST=1               fast daily mode (canonical/recent rows + dashboard-only mirror sync)
#   GMAIL_SINCE_DAYS=14            bound IMAP fetch when ingest runs
#   ORIGENLAB_GMAIL_SENT_FOLDER    default "[Gmail]/Enviados"
#   ORIGENLAB_EXPECT_EQUIPMENT_COUNT  default 9 (verify assertion)
#   ORIGENLAB_SYNC_UPDATED_BY / ORIGENLAB_SYNC_REASON  passed to mirror sync
#
# See docs/REFRESH_RENDER_DASHBOARD_ONCE.md
set -eo pipefail

PIPE="$(cd "$(dirname "$0")/../.." && pwd)"

# shellcheck source=scripts/ops/_load_pipeline_dotenv.sh
source "${PIPE}/scripts/ops/_load_pipeline_dotenv.sh"
load_pipeline_dotenv "$PIPE"

SQLITE_PATH="${ORIGENLAB_SQLITE_PATH:-$HOME/data/origenlab-email/sqlite/emails.sqlite}"
CLOUD_PG_URL="${ORIGENLAB_CLOUD_POSTGRES_URL:-}"
RUN_GMAIL_INGEST="${RUN_GMAIL_INGEST:-0}"
RUN_COMMERCIAL_DEAL_MIRROR="${RUN_COMMERCIAL_DEAL_MIRROR:-0}"
DASHBOARD_FAST="${DASHBOARD_FAST:-0}"
GMAIL_SINCE_DAYS="${GMAIL_SINCE_DAYS:-14}"
GMAIL_SENT_FOLDER="${ORIGENLAB_GMAIL_SENT_FOLDER:-[Gmail]/Enviados}"
EXPECT_EQUIPMENT="${ORIGENLAB_EXPECT_EQUIPMENT_COUNT:-9}"
DASHBOARD_VERIFY_JSON="/tmp/render_dashboard_mirror_verify.json"
COMMERCIAL_VERIFY_JSON="/tmp/commercial_deals_mirror_verify.json"

_canonical_gmail_count_sql() {
  sqlite3 "$SQLITE_PATH" \
    "SELECT COUNT(*), MAX(date_iso) FROM emails WHERE source_file LIKE 'gmail:contacto@origenlab.cl/%';"
}

echo "== OrigenLab: refresh Render dashboard once =="
echo "Safety: no sends, no Gmail mutation, no mart/commercial --rebuild, no outreach writes, no deploy."
if [[ "$DASHBOARD_FAST" == "1" ]]; then
  echo "Mode: DASHBOARD_FAST=1 (incremental canonical refresh + dashboard-only Postgres sync)"
else
  echo "Mode: default (full mart scan + standard mirror sync)"
fi

if [[ ! -f "$SQLITE_PATH" ]]; then
  echo "ERROR: SQLite not found: $SQLITE_PATH" >&2
  echo "Set ORIGENLAB_SQLITE_PATH to the local canonical DB." >&2
  exit 2
fi

if [[ -z "$CLOUD_PG_URL" ]]; then
  echo "ERROR: ORIGENLAB_CLOUD_POSTGRES_URL is not set (Render external Postgres URL)." >&2
  exit 2
fi

export ORIGENLAB_SQLITE_PATH="$SQLITE_PATH"
export ORIGENLAB_CLOUD_POSTGRES_URL="$CLOUD_PG_URL"

cd "$PIPE"

# Fail early on placeholder/invalid URL; export psycopg URL for sync + verify in this shell.
# shellcheck source=scripts/ops/_cloud_postgres_env.sh
source "${PIPE}/scripts/ops/_cloud_postgres_env.sh"
if ! cloud_postgres_prepare_env "$PIPE"; then
  exit 2
fi

echo ""
echo "-- Preflight: SQLite readable (canonical Gmail count before) --"
SQLITE_CANONICAL_BEFORE="$(_canonical_gmail_count_sql)"
echo "$SQLITE_CANONICAL_BEFORE"

if [[ "$RUN_GMAIL_INGEST" == "1" ]]; then
  echo ""
  echo "-- Optional Gmail ingest (read-only IMAP; new messages only) --"
  uv sync --group gmail --group dev >/dev/null
  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py \
    --folder INBOX \
    --skip-duplicate-message-id \
    --since-days "$GMAIL_SINCE_DAYS"
  uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py \
    --folder "$GMAIL_SENT_FOLDER" \
    --skip-duplicate-message-id \
    --since-days "$GMAIL_SINCE_DAYS"
  echo ""
  echo "-- After ingest (canonical Gmail count) --"
  echo "$(_canonical_gmail_count_sql)"
else
  echo ""
  echo "-- Gmail ingest skipped (set RUN_GMAIL_INGEST=1 to fetch new mail) --"
fi

echo ""
echo "-- Incremental SQLite derived layers (no --rebuild) --"
uv sync --group dev >/dev/null
if [[ "$DASHBOARD_FAST" == "1" ]]; then
  FAST_SINCE_DAYS="${GMAIL_SINCE_DAYS:-14}"
  uv run python scripts/mart/build_business_mart.py \
    --dashboard-fast \
    --canonical-only \
    --since-days "$FAST_SINCE_DAYS" \
    --skip-document-master-if-unchanged
else
  uv run python scripts/mart/build_business_mart.py
fi
uv run python scripts/commercial/build_commercial_intel_v1.py

echo ""
echo "-- Canonical Gmail count after derived layers (before Postgres sync) --"
SQLITE_CANONICAL_AFTER="$(_canonical_gmail_count_sql)"
echo "$SQLITE_CANONICAL_AFTER"

echo ""
echo "-- Sync dashboard mirror → Render Postgres --"
if [[ "$DASHBOARD_FAST" == "1" ]]; then
  uv run alembic -c alembic.ini upgrade head
  uv run python scripts/sync/sync_dashboard_postgres_mirror.py \
    --allow-non-scratch-postgres \
    --only canonical \
    --include-equipment-opportunities \
    --include-warm-cases \
    --updated-by "${ORIGENLAB_SYNC_UPDATED_BY:-phase1-cloud-manual}" \
    --reason "${ORIGENLAB_SYNC_REASON:-Phase 6.6 dashboard-fast canonical mirror sync}" \
    --json-out /tmp/phase1_cloud_mirror_sync.json
else
  bash scripts/ops/sync_dashboard_mirror_to_cloud.sh
fi

echo ""
echo "-- Verify mirror (assert Render dashboard readiness) --"
uv run python scripts/qa/verify_dashboard_postgres_mirror.py \
  --assert-render-dashboard \
  --expect-equipment-count "$EXPECT_EQUIPMENT" \
  --json-out "$DASHBOARD_VERIFY_JSON"

COMMERCIAL_MIRROR_STATUS="skipped"
GMAIL_INGEST_LABEL="off"
COMMERCIAL_MIRROR_LABEL="off"
[[ "$RUN_GMAIL_INGEST" == "1" ]] && GMAIL_INGEST_LABEL="on"
[[ "$RUN_COMMERCIAL_DEAL_MIRROR" == "1" ]] && COMMERCIAL_MIRROR_LABEL="on"

if [[ "$RUN_COMMERCIAL_DEAL_MIRROR" == "1" ]]; then
  # shellcheck source=scripts/ops/_refresh_commercial_deal_mirror.sh
  source "${PIPE}/scripts/ops/_refresh_commercial_deal_mirror.sh"
  if run_commercial_deal_mirror_refresh "$PIPE" "$COMMERCIAL_VERIFY_JSON"; then
    COMMERCIAL_MIRROR_STATUS="ok"
  else
    COMMERCIAL_MIRROR_STATUS="failed"
    exit 1
  fi
fi

echo ""
echo "============================================================"
echo "Render dashboard mirror refresh complete."
echo ""
echo "Summary:"
echo "  Gmail ingest:              $GMAIL_INGEST_LABEL"
echo "  Dashboard fast mode:       ${DASHBOARD_FAST}"
echo "  SQLite canonical (before): $SQLITE_CANONICAL_BEFORE"
echo "  SQLite canonical (after):  $SQLITE_CANONICAL_AFTER"
echo "  Dashboard mirror verify:   $DASHBOARD_VERIFY_JSON"
echo "  Commercial deal mirror:    $COMMERCIAL_MIRROR_LABEL ($COMMERCIAL_MIRROR_STATUS)"
if [[ "$RUN_COMMERCIAL_DEAL_MIRROR" == "1" ]]; then
  echo "  Commercial verify JSON:    $COMMERCIAL_VERIFY_JSON"
fi
echo "  Sends / outreach / deploy: not run (read-only refresh)"
echo ""
echo "Open dashboard and click Refresh."
echo "============================================================"
