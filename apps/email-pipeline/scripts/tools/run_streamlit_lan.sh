#!/usr/bin/env bash
# LEGACY (parked): Streamlit LAN launcher — not the active operator UI (use apps/dashboard).
# Scheduled for removal; see docs/audits/STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md
#
# Run Business Mart Streamlit so other machines on the LAN can open it.
# Binds 0.0.0.0 (not only localhost). On WSL2 you still need Windows portproxy
# + firewall for your Wi‑Fi IP → WSL (see README legacy Streamlit section).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${STREAMLIT_PORT:-8501}"
cd "$ROOT"
exec uv run --group ui streamlit run apps/business_mart_app.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT"
