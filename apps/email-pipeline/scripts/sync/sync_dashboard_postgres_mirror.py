#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY: Read-only SQLite; writes Postgres dashboard mirror tables only via
# existing migrate loaders (--replace on scratch/staging). No Gmail ingest, no
# mart rebuild, no email send. See docs/RUNBOOK.md — "Refresh Postgres dashboard mirror".
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
