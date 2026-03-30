#!/usr/bin/env bash
# Run Business Mart Streamlit so other machines on the LAN can open it.
# Binds 0.0.0.0 (not only localhost). On WSL2 you still need Windows portproxy
# + firewall for your Wi‑Fi IP → WSL (see README "Streamlit on LAN (WSL2)").
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${STREAMLIT_PORT:-8501}"
cd "$ROOT"
exec uv run --group ui streamlit run apps/business_mart_app.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT"
