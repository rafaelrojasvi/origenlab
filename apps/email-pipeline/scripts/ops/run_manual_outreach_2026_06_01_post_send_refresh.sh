#!/usr/bin/env bash
# Post-send refresh after 2026-06-01 manual prospect outreach + Cyber BCC extra.
# Read-only Gmail ingest; SQLite mutations for suppressions/contacted; Postgres mirror.
set -eo pipefail

PIPE="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/ops/_load_pipeline_dotenv.sh
source "${PIPE}/scripts/ops/_load_pipeline_dotenv.sh"
load_pipeline_dotenv "$PIPE"

cd "$PIPE"
OUT="${PIPE}/reports/out/active/current"
STAGE="${OUT}/_staging_manual_outreach_2026-06-01"
UPDATED_BY="manual_outreach_2026_06_01"
SINCE_DAYS="${SINCE_DAYS:-3}"

mkdir -p "$STAGE"

cat >"$STAGE/manual_prospect_all.txt" <<'EOF'
giba@udec.cl
kpena@cslab.cl
pamela.munoz@uach.cl
hannelore.valentin@sgs.com
ambiental@silobchile.cl
udt@udt.cl
mfbarrar@ug.uchile.cl
jmieville@wss.cl
ccorporativas@hcuch.cl
EOF

cat >"$STAGE/manual_prospect_delivered.txt" <<'EOF'
giba@udec.cl
kpena@cslab.cl
pamela.munoz@uach.cl
ambiental@silobchile.cl
udt@udt.cl
EOF

cat >"$STAGE/cyber_bcc_all.txt" <<'EOF'
mle@mlelab.cl
laboratorio@condecal.cl
monica.cisternas@dukay.cl
catalina.vera@ibbeta.cl
contacto@lacofar.cl
pcanales@mrlab.cl
mlortiz@difrecalcine.cl
asegcalidad@coesam.cl
secretaria@colorbel.cl
omeneses@cosmeticanacional.cl
dfuente@durandin.cl
mchicago@aramalab.cl
plizama@labomed.cl
rdoria@maver.cl
vmoyer@maver.cl
gstorme@mintlab.cl
edith.yanez@dragpharma.cl
EOF

echo "== 1) Gmail ingest (INBOX + Enviados, ${SINCE_DAYS}d) =="
uv sync --group gmail --group dev >/dev/null
uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py \
  --folder INBOX \
  --since-days "$SINCE_DAYS" \
  --skip-duplicate-message-id
uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py \
  --folder "[Gmail]/Enviados" \
  --since-days "$SINCE_DAYS" \
  --skip-duplicate-message-id

echo "== 2) NDR scan → contact_email_suppression =="
uv run python scripts/tools/flag_ndr_bounces_from_contacto.py \
  --since-days "$SINCE_DAYS" \
  --apply

echo "== 3) Batch bounce sync (manual + cyber) =="
uv run python scripts/qa/sync_outreach_batch_from_ingested_bounces.py \
  --batch-file "$STAGE/manual_prospect_all.txt" \
  --since-days "$SINCE_DAYS" \
  --apply \
  --updated-by "$UPDATED_BY"
uv run python scripts/qa/sync_outreach_batch_from_ingested_bounces.py \
  --batch-file "$STAGE/cyber_bcc_all.txt" \
  --since-days "$SINCE_DAYS" \
  --apply \
  --updated-by "$UPDATED_BY"

echo "== 4) Mark delivered manual prospects contacted =="
uv run python scripts/leads/mark_sent_batch_contacted.py \
  --batch-file "$STAGE/manual_prospect_delivered.txt" \
  --source manual_prospect_outreach_2026_06_01 \
  --notes "manual_prospect_outreach" \
  --updated-by "$UPDATED_BY"

echo "== 5) Mark Cyber BCC as contacted (campaign memory) =="
uv run python scripts/leads/mark_sent_batch_contacted.py \
  --batch-file "$STAGE/cyber_bcc_all.txt" \
  --source cyber_bcc_extra_2026_06_01 \
  --notes "campaign_outreach/cyber_bcc_extra" \
  --updated-by "$UPDATED_BY"

echo "== 6) Outbound safety memory exports =="
uv run python scripts/qa/refresh_outbound_safety_memory.py

echo "== 7) Marts + commercial intel =="
uv run python scripts/mart/build_business_mart.py
uv run python scripts/commercial/build_commercial_intel_v1.py

echo "== 8) Contacted universe audit =="
uv run python scripts/leads/audit_contacted_universe.py

echo "== 9) Presentation + Cyber QA rebuilds =="
uv run python scripts/qa/build_presentacion_origenlab_review.py || true
uv run python scripts/qa/build_presentacion_origenlab_quality.py || true
uv run python scripts/qa/build_presentacion_batch1_presend_audit.py || true
uv run python scripts/qa/build_cyber_outreach_campaign.py || true
uv run python scripts/qa/build_cyber_campaign_context_audit.py || true

echo "== 10) Lead research SQLite + presentación merge =="
uv run python scripts/leads/build_lead_research_sqlite.py || true
uv run python scripts/qa/build_presentacion_prospectos_merge.py || true

echo "== 11) Postgres mirror (dashboard + lead + outbound sidecars) =="
GMAIL_SINCE_DAYS=0 RUN_GMAIL_INGEST=0 DASHBOARD_FAST=1 RUN_LEAD_RESEARCH_MIRROR=1 RUN_OUTBOUND_SIDECAR_MIRROR=1 \
  ORIGENLAB_SYNC_REASON=manual_outreach_2026_06_01 \
  ORIGENLAB_SYNC_UPDATED_BY="$UPDATED_BY" \
  bash scripts/ops/refresh_render_dashboard_once.sh

echo "== 12) Digest + verification reports =="
uv run python scripts/qa/build_manual_outreach_2026_06_01_digest.py --since-days "$SINCE_DAYS"

echo "Done. Reports under ${OUT}/manual_outreach_2026-06-01_*"
