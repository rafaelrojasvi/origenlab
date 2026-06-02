#!/usr/bin/env python3
"""COMPATIBILITY_WRAPPER (COMPATIBILITY_ONLY) — lead-account → org match CLI.

- **Canonical implementation:** ``scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py`` (**use for new docs and agent prompts**).
- **Not preferred** for new operator commands; this root path delegates only.
- This **root** path exists for older commands that call ``scripts/match_lead_accounts_to_existing_orgs.py``.
- **Do not delete** until docs, tests, and operator flows no longer reference this path.
- **No behavior** beyond delegation; do not add logic here.
"""

from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

_WARNINGS = Path(__file__).resolve().parent / "_script_warnings.py"
_spec = importlib.util.spec_from_file_location("_script_warnings", _WARNINGS)
assert _spec and _spec.loader
_sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sw)

_IMPLEMENTATION = (
    Path(__file__).resolve().parent / "leads" / "advanced" / "match_lead_accounts_to_existing_orgs.py"
)

if __name__ == "__main__":
    _sw.print_wrapper_deprecation_warning(
        "scripts/match_lead_accounts_to_existing_orgs.py",
        "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py",
    )
    sys.argv[0] = str(_IMPLEMENTATION)
    runpy.run_path(str(_IMPLEMENTATION), run_name="__main__")
