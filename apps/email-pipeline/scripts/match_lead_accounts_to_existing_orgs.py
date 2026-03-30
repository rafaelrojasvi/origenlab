#!/usr/bin/env python3
"""Compatibility wrapper — implementation: ``scripts/leads/match_lead_accounts_to_existing_orgs.py``."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_IMPLEMENTATION = Path(__file__).resolve().parent / "leads" / "match_lead_accounts_to_existing_orgs.py"

if __name__ == "__main__":
    sys.argv[0] = str(_IMPLEMENTATION)
    runpy.run_path(str(_IMPLEMENTATION), run_name="__main__")
