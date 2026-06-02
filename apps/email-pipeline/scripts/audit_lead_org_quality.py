#!/usr/bin/env python3
"""COMPATIBILITY_WRAPPER (COMPATIBILITY_ONLY) — org-quality audit CLI.

- **Canonical implementation:** ``scripts/leads/advanced/audit_lead_org_quality.py`` (**use for new docs and agent prompts**).
- **Not preferred** for new operator commands; this root path delegates only.
- This **root** path keeps legacy ``scripts/audit_lead_org_quality.py`` invocations working.
- **Do not delete** until docs, tests, and operator references no longer need this path.
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

_IMPLEMENTATION = Path(__file__).resolve().parent / "leads" / "advanced" / "audit_lead_org_quality.py"

if __name__ == "__main__":
    _sw.print_wrapper_deprecation_warning(
        "scripts/audit_lead_org_quality.py",
        "scripts/leads/advanced/audit_lead_org_quality.py",
    )
    sys.argv[0] = str(_IMPLEMENTATION)
    runpy.run_path(str(_IMPLEMENTATION), run_name="__main__")
