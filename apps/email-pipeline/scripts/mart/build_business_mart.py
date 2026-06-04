#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Rebuild path deletes mart tables (contact_master, etc.)
# before repopulating. Run only when you intend a full mart refresh.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Build the client-facing business mart tables (reproducible).

This script materializes:
- contact_master
- organization_master
- document_master
- opportunity_signals

Raw archive tables are not modified.

**Source tiers:** the mart scans **all** rows in ``emails`` (mbox/PST legacy plus Workspace Gmail).
Operational views (dashboard/API, outbound readiness, case queues) default to **canonical** rows
``gmail:contacto@origenlab.cl/…`` only — see :mod:`origenlab_email_pipeline.contacto_gmail_source`
and ``docs/RUNBOOK.md`` (source of truth).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.core.mart.build_business_mart_cli import run_build_business_mart_from_argv


def main() -> None:
    raise SystemExit(run_build_business_mart_from_argv())


if __name__ == "__main__":
    main()
