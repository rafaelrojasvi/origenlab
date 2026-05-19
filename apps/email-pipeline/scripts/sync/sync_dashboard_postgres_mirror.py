#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# EXPERIMENTAL_PARKED: Dashboard Postgres mirror only — not send/export truth.
# SQLite + Gmail Sent remain operational source of truth. Do not run without explicit
# operator approval. See docs/EXPERIMENTAL_PARKED.md.
# -----------------------------------------------------------------------------
# SAFETY: Read-only SQLite; writes Postgres dashboard mirror tables only via
# existing migrate loaders (--replace on scratch/staging). No Gmail ingest, no
# mart rebuild, no email send. Fails closed if canonical Gmail rows exist but SQLite
# mart tables are empty (use --allow-empty-mart break-glass only).
# See docs/RUNBOOK.md — "Refresh Postgres dashboard mirror".
# -----------------------------------------------------------------------------
"""Refresh Postgres dashboard mirror from SQLite (outbound sidecars + mart core)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.dashboard_postgres_sync import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
