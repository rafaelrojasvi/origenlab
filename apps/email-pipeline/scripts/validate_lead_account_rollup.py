#!/usr/bin/env python3
"""COMPATIBILITY_WRAPPER (COMPATIBILITY_ONLY) — lead-account rollup validation CLI.

- **Canonical implementation:** ``scripts/leads/advanced/validate_lead_account_rollup.py`` (**use for new docs and agent prompts**).
- **Not preferred** for new operator commands; this root path delegates only.
- This **root** path keeps ``scripts/validate_lead_account_rollup.py`` working for legacy tooling.
- **Do not delete** until docs, tests, and operator references no longer need this path.
- **No behavior** beyond delegation; do not add logic here.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_IMPLEMENTATION = (
    Path(__file__).resolve().parent / "leads" / "advanced" / "validate_lead_account_rollup.py"
)

if __name__ == "__main__":
    sys.argv[0] = str(_IMPLEMENTATION)
    runpy.run_path(str(_IMPLEMENTATION), run_name="__main__")
