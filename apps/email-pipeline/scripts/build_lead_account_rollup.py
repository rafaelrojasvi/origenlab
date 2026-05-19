#!/usr/bin/env python3
"""COMPATIBILITY_WRAPPER (COMPATIBILITY_ONLY) — lead-account rollup CLI.

- **Canonical implementation:** ``scripts/leads/advanced/build_lead_account_rollup.py`` (**use for new docs and agent prompts**).
- **Not preferred** for new operator commands; this root path delegates only.
- This **root** path exists so older bookmarks, shell one-liners, and tests that invoke
  ``scripts/build_lead_account_rollup.py`` keep working.
- **Do not delete** this file until nothing in docs, tests, or operator flows references this path
  (see also ``test_critical_script_paths`` and ``SCRIPT_MAP.md``).
- **No behavior** beyond delegating to the file above; do not add logic here.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_IMPLEMENTATION = (
    Path(__file__).resolve().parent / "leads" / "advanced" / "build_lead_account_rollup.py"
)

if __name__ == "__main__":
    sys.argv[0] = str(_IMPLEMENTATION)
    runpy.run_path(str(_IMPLEMENTATION), run_name="__main__")
