#!/usr/bin/env bash
# One ordered operational routine for leads + client pack + publish gate.
#
# Order (fail-fast except publish_gate records manifest even on gate failure):
#   0. Generate operational_run_id (UUID) and export ORIGENLAB_LEADS_OPERATIONAL_RUN_ID
#   1. Optional file ingest (same env as run_leads_pipeline.sh)
#   2. Ensure lead schema — normalize_leads.py --ensure-schema-only
#   3. Normalize — normalize_leads.py (external_leads_raw → lead_master)
#   4. Reconcile upstream — reconcile_lead_upstream.py (--apply by default)
#   5. Score — leads_score.py
#   6. Match — match_leads_to_mart.py
#   7. Exports — export_leads_csv.py + export_leads_shortlist.py
#   8. Weekly focus — run_weekly_focus.py (skip with --skip-focus)
#   9. Client pack — build_leads_client_pack.py (skip with --skip-pack)
#   10. Publish gate — publish_gate.py (skip with --skip-gate)
#   11. Stack manifest — write_operational_stack_provenance.py →
#       reports/out/active/operational_stack_last_run.json
#       and reports/out/active/operational_run_manifests/<run_id>.json
#
# --reconcile-dry-run runs reconcile_lead_upstream.py without --apply only. Normalize, score,
# match, exports, weekly focus, and client pack still write the SQLite DB and/or report files;
# this is not a read-only or whole-stack dry run.
#
# This script does NOT build the business mart. Match quality needs mart rows; run first e.g.:
#   bash scripts/pipeline/run_aligned_stack.sh
# or: uv run python scripts/mart/build_business_mart.py
#
# Usage (from apps/email-pipeline repo root):
#   bash scripts/leads/run_leads_operational_stack.sh
#   bash scripts/leads/run_leads_operational_stack.sh --skip-fetch
#   bash scripts/leads/run_leads_operational_stack.sh --reconcile-dry-run
#   bash scripts/leads/run_leads_operational_stack.sh --skip-gate
#   bash scripts/leads/run_leads_operational_stack.sh --skip-pack
#   bash scripts/leads/run_leads_operational_stack.sh --skip-focus
#   bash scripts/leads/run_leads_operational_stack.sh --db /path/to/emails.sqlite
#
# Env (ingest): LEADS_CHILECOMPRA_FILE, LEADS_INN_FILE, LEADS_CORFO_FILE
# Env (exports): LEADS_EXPORT_PATH, LEADS_SHORTLIST_PATH, LEADS_SHORTLIST_LIMIT
# Env (DB): ORIGENLAB_SQLITE_PATH (or --db: exported for child processes and passed to publish_gate)
# Env (run correlation): ORIGENLAB_LEADS_OPERATIONAL_RUN_ID, ORIGENLAB_LEADS_OPERATIONAL_STACK_STARTED_AT
#   (set by this script; publish_gate and client pack read the run_id)
#
# If a step before publish_gate fails, the manifest is not written (same as before).
# If publish_gate fails, step 11 still runs so operational_stack_last_run.json records
# publish_gate.passed=false for this run_id.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

SKIP_FETCH=0
SKIP_GATE=0
SKIP_PACK=0
SKIP_FOCUS=0
RECONCILE_DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-fetch) SKIP_FETCH=1; shift ;;
    --skip-gate) SKIP_GATE=1; shift ;;
    --skip-pack) SKIP_PACK=1; shift ;;
    --skip-focus) SKIP_FOCUS=1; shift ;;
    --reconcile-dry-run) RECONCILE_DRY_RUN=1; shift ;;
    --db)
      if [[ $# -lt 2 ]]; then echo "--db requires a path" >&2; exit 2; fi
      export ORIGENLAB_SQLITE_PATH="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,48p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)" >&2
      exit 2
      ;;
  esac
done

RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
STACK_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export ORIGENLAB_LEADS_OPERATIONAL_RUN_ID="$RUN_ID"
export ORIGENLAB_LEADS_OPERATIONAL_STACK_STARTED_AT="$STACK_STARTED_AT"

LEADS_EXPORT_PATH="${LEADS_EXPORT_PATH:-$ROOT/reports/out/leads_export.csv}"
LEADS_CHILECOMPRA_FILE="${LEADS_CHILECOMPRA_FILE:-}"
LEADS_INN_FILE="${LEADS_INN_FILE:-}"
LEADS_CORFO_FILE="${LEADS_CORFO_FILE:-}"
SHORTLIST_PATH="${LEADS_SHORTLIST_PATH:-$ROOT/reports/out/leads_shortlist.csv}"

GATE_DB_ARGS=()
if [[ -n "${ORIGENLAB_SQLITE_PATH:-}" ]]; then
  GATE_DB_ARGS=(--db "$ORIGENLAB_SQLITE_PATH")
fi

echo "========== OrigenLab leads operational stack =========="
echo "Repo: $ROOT"
echo "Operational run_id: $RUN_ID"
if [[ -n "${ORIGENLAB_SQLITE_PATH:-}" ]]; then
  echo "SQLite: $ORIGENLAB_SQLITE_PATH"
else
  echo "SQLite: (default from config / ORIGENLAB_SQLITE_PATH)"
fi
echo "Note: ensure business mart is built if you need meaningful lead↔archive matches."
echo ""

step=0
next_step() { step=$((step + 1)); echo ">>> Step $step: $*"; }

if [[ "$SKIP_FETCH" == 0 ]]; then
  if [[ -n "$LEADS_CHILECOMPRA_FILE" && -f "$LEADS_CHILECOMPRA_FILE" ]]; then
    next_step "Ingest ChileCompra"
    uv run python scripts/leads/fetch_chilecompra.py --file "$LEADS_CHILECOMPRA_FILE"
  elif [[ -n "$LEADS_CHILECOMPRA_FILE" ]]; then
    echo ">>> Skip ChileCompra (file not found: $LEADS_CHILECOMPRA_FILE)"
  else
    echo ">>> Skip ChileCompra (LEADS_CHILECOMPRA_FILE unset)"
  fi
  if [[ -n "$LEADS_INN_FILE" && -f "$LEADS_INN_FILE" ]]; then
    next_step "Ingest INN labs"
    uv run python scripts/leads/fetch_inn_labs.py --file "$LEADS_INN_FILE"
  elif [[ -n "$LEADS_INN_FILE" ]]; then
    echo ">>> Skip INN (file not found: $LEADS_INN_FILE)"
  else
    echo ">>> Skip INN (LEADS_INN_FILE unset)"
  fi
  if [[ -n "$LEADS_CORFO_FILE" && -f "$LEADS_CORFO_FILE" ]]; then
    next_step "Ingest CORFO centers"
    uv run python scripts/leads/fetch_corfo_centers.py --file "$LEADS_CORFO_FILE"
  elif [[ -n "$LEADS_CORFO_FILE" ]]; then
    echo ">>> Skip CORFO (file not found: $LEADS_CORFO_FILE)"
  else
    echo ">>> Skip CORFO (LEADS_CORFO_FILE unset)"
  fi
else
  echo ">>> Skip fetch (--skip-fetch)"
fi
echo ""

next_step "Ensure lead schema"
uv run python scripts/leads/normalize_leads.py --ensure-schema-only

next_step "Normalize lead_master from external_leads_raw"
uv run python scripts/leads/normalize_leads.py

if [[ "$RECONCILE_DRY_RUN" == 1 ]]; then
  next_step "Reconcile upstream (dry-run)"
  uv run python scripts/leads/reconcile_lead_upstream.py
else
  next_step "Reconcile upstream (apply soft-retire)"
  uv run python scripts/leads/reconcile_lead_upstream.py --apply
fi

next_step "Score leads"
uv run python scripts/leads/leads_score.py

next_step "Match leads to mart"
uv run python scripts/leads/match_leads_to_mart.py

next_step "Export leads CSV + shortlist"
mkdir -p "$(dirname "$LEADS_EXPORT_PATH")" "$(dirname "$SHORTLIST_PATH")"
uv run python scripts/leads/export_leads_csv.py --out "$LEADS_EXPORT_PATH"
uv run python scripts/leads/export_leads_shortlist.py --out "$SHORTLIST_PATH" --limit "${LEADS_SHORTLIST_LIMIT:-200}"

if [[ "$SKIP_FOCUS" == 0 ]]; then
  next_step "Weekly focus (reports/out/active)"
  uv run python scripts/leads/run_weekly_focus.py
else
  echo ">>> Skip weekly focus (--skip-focus)"
fi

if [[ "$SKIP_PACK" == 0 ]]; then
  next_step "Client pack"
  uv run python scripts/reports/build_leads_client_pack.py
else
  echo ">>> Skip client pack (--skip-pack)"
fi

PUBLISH_GATE_EXIT=""
if [[ "$SKIP_GATE" == 0 ]]; then
  next_step "Publish gate"
  set +e
  uv run python scripts/qa/publish_gate.py "${GATE_DB_ARGS[@]}"
  PUBLISH_GATE_EXIT=$?
  set -e
else
  echo ">>> Skip publish gate (--skip-gate)"
fi

STACK_REC_MODE=apply
if [[ "$RECONCILE_DRY_RUN" == 1 ]]; then
  STACK_REC_MODE=dry_run
fi
next_step "Write operational stack manifest (active/ + run archive)"
GATE_ARG=()
if [[ "$SKIP_GATE" == 0 ]]; then
  GATE_ARG=(--publish-gate-exit "$PUBLISH_GATE_EXIT")
fi
uv run python scripts/leads/write_operational_stack_provenance.py \
  --run-id "$RUN_ID" \
  --started-at-utc "$STACK_STARTED_AT" \
  --reconcile-mode "$STACK_REC_MODE" \
  --skip-fetch "$SKIP_FETCH" \
  --skip-focus "$SKIP_FOCUS" \
  --skip-pack "$SKIP_PACK" \
  --skip-gate "$SKIP_GATE" \
  "${GATE_ARG[@]}"

FINAL_EXIT=0
if [[ "$SKIP_GATE" == 0 && "$PUBLISH_GATE_EXIT" -ne 0 ]]; then
  FINAL_EXIT="$PUBLISH_GATE_EXIT"
fi

echo ""
echo "========== Operational stack complete =========="
echo "Export: $LEADS_EXPORT_PATH"
echo "Shortlist: $SHORTLIST_PATH"
echo "Client pack: $ROOT/reports/out/client_pack_latest/"
echo "Weekly focus: $ROOT/reports/out/active/leads_weekly_focus.csv"
echo "Run manifest: $ROOT/reports/out/active/operational_stack_last_run.json"
echo "Run archive:  $ROOT/reports/out/active/operational_run_manifests/${RUN_ID}.json"
if [[ "$RECONCILE_DRY_RUN" == 1 ]]; then
  echo ""
  echo "NOTE: --reconcile-dry-run was used — upstream reconcile did not apply soft-retire."
  echo "      Normalize, score, match, exports, and any focus/pack steps still wrote DB/files as usual."
fi
if [[ "$SKIP_GATE" == 1 ]]; then
  echo ""
  echo "NOTE: --skip-gate — publish validation did NOT run. This completion is NOT publish-safe by default."
  echo "      publish_gate.executed is false in the manifest; do not treat outputs as gate-validated."
  echo "      Before external handoff, run:"
  echo "        uv run python scripts/qa/publish_gate.py"
elif [[ "$SKIP_PACK" == 1 ]]; then
  echo ""
  echo "NOTE: --skip-pack — client pack was not rebuilt; publish_gate (if run) checks the existing pack on disk."
fi
if [[ "$SKIP_GATE" == 0 && "$PUBLISH_GATE_EXIT" -ne 0 ]]; then
  echo ""
  echo "NOTE: publish_gate failed (exit $PUBLISH_GATE_EXIT). Manifest records publish_gate.passed=false for run_id $RUN_ID."
fi

exit "$FINAL_EXIT"
