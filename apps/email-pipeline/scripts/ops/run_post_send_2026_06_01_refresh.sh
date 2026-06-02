#!/usr/bin/env bash
# Post-send refresh: manual outreach + mom additional sends (read-only Gmail ingest).
#
# HISTORICAL ONE-OFF — 2026-06-01 campaign window only.
# Canonical procedure for new post-send work: docs/pipeline/POST_SEND_SAFE_LOOP.md
# (do not copy this file blindly; step 2 still uses broad NDR --apply — see warning below).
#
# When cloning for a future wave, follow POST_SEND_SAFE_LOOP.md: ingest → NDR dry-run →
# targeted allowlist apply → contacted → safety → digest → mirror → drift audit.
set -eo pipefail

PIPE="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/ops/_load_pipeline_dotenv.sh
source "${PIPE}/scripts/ops/_load_pipeline_dotenv.sh"
load_pipeline_dotenv "$PIPE"

cd "$PIPE"
OUT="${PIPE}/reports/out/active/current"
SINCE_DAYS="${SINCE_DAYS:-2}"
UPDATED_BY="post_send_2026_06_01"

echo "== 1) Gmail ingest INBOX + Enviados (${SINCE_DAYS}d, no replace-source) =="
uv sync --group gmail --group dev >/dev/null
INBOX_STATS=$(uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py \
  --folder INBOX --since-days "$SINCE_DAYS" --skip-duplicate-message-id 2>&1 | tail -5)
SENT_STATS=$(uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py \
  --folder "[Gmail]/Enviados" --since-days "$SINCE_DAYS" --skip-duplicate-message-id 2>&1 | tail -5)
echo "$INBOX_STATS"
echo "$SENT_STATS"

echo "== 2) NDR scan → exact contact_email_suppression =="
cat <<'WARN' >&2
*** NDR APPLY WARNING (historical script — read before continuing) ***
  This one-off still runs BROAD: flag_ndr_bounces_from_contacto.py --apply
  That applies ALL planned NDR recipients in the scan window — break-glass behavior.

  For new work, do NOT use broad --apply by default:
    1) Dry-run first (omit --apply).
    2) Review recipients; build an allowlist (one email per line).
    3) Apply only with: --emails-file PATH --only-code CODE --apply
       (exact-email only; no domain suppression).
    4) Skip delay DSNs; stop for operator review if unsure.

  Canonical doc: docs/pipeline/POST_SEND_SAFE_LOOP.md
***
WARN
uv run python scripts/tools/flag_ndr_bounces_from_contacto.py \
  --since-days "$SINCE_DAYS" --apply

echo "== 3) Backfill contacted from Sent (outreach_contact_state) =="
uv run python scripts/leads/backfill_contacted_from_gmail_sent.py --apply \
  --updated-by "$UPDATED_BY" --source "post_send_gmail_sent_${SINCE_DAYS}d"

echo "== 4) Prior batch bounce sync (2026-06-01 manual + cyber) =="
STAGE="${OUT}/_staging_manual_outreach_2026-06-01"
if [[ -d "$STAGE" ]]; then
  for f in manual_prospect_all.txt cyber_bcc_all.txt; do
    if [[ -f "$STAGE/$f" ]]; then
      uv run python scripts/qa/sync_outreach_batch_from_ingested_bounces.py \
        --batch-file "$STAGE/$f" --since-days "$SINCE_DAYS" --apply --updated-by "$UPDATED_BY"
    fi
  done
fi

echo "== 5) Outbound safety memory =="
uv run python scripts/qa/refresh_outbound_safety_memory.py

echo "== 6) Contacted universe audit =="
uv run python scripts/leads/audit_contacted_universe.py

echo "== 7) Marts + commercial intel =="
uv run python scripts/mart/build_business_mart.py
uv run python scripts/commercial/build_commercial_intel_v1.py

echo "== 8) Campaign / presentation / legacy review rebuilds =="
uv run python scripts/qa/build_cyber_outreach_campaign.py || true
uv run python scripts/qa/build_presentacion_origenlab_review.py || true
uv run python scripts/qa/build_presentacion_origenlab_quality.py || true
uv run python scripts/qa/build_legacy_contacts_2016_2019_review.py || true
uv run python scripts/qa/build_presentacion_prospectos_merge.py || true

echo "== 9) Postgres mirror =="
GMAIL_SINCE_DAYS=0 RUN_GMAIL_INGEST=0 DASHBOARD_FAST=1 RUN_LEAD_RESEARCH_MIRROR=1 RUN_OUTBOUND_SIDECAR_MIRROR=1 \
  ORIGENLAB_SYNC_REASON=post_send_2026_06_01 \
  ORIGENLAB_SYNC_UPDATED_BY="$UPDATED_BY" \
  bash scripts/ops/refresh_render_dashboard_once.sh

echo "== 10) Post-send digest =="
uv run python scripts/qa/build_post_send_digest.py --since-days "$SINCE_DAYS"

echo "== 11) Mirror verify =="
uv run python scripts/qa/verify_outbound_sidecar_postgres_mirror.py --json-out /tmp/outbound_sidecar_mirror_verify.json || true
uv run python scripts/qa/verify_lead_research_postgres_mirror.py || true

echo "== 12) Prospectos safety drift audit (report-only; optional strict) =="
DRIFT_ARGS=()
if [[ "${ORIGENLAB_STRICT_PROSPECTOS_DRIFT:-0}" == "1" ]]; then
  DRIFT_ARGS=(--strict)
  echo "  STRICT: ORIGENLAB_STRICT_PROSPECTOS_DRIFT=1 — drift thresholds fail this step."
else
  echo "  Report-only (set ORIGENLAB_STRICT_PROSPECTOS_DRIFT=1 to fail on drift thresholds)."
fi
uv run python scripts/qa/audit_prospectos_safety_drift.py "${DRIFT_ARGS[@]}"

echo "Done. Reports: ${OUT}/post_send_*_2026-06-01.* and ${OUT}/prospectos_safety_drift_*"
