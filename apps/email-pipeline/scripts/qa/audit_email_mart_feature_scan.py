#!/usr/bin/env python3
"""Read-only parity audit: old email scan vs email_mart_features scan.

Does not rebuild contact_master, organization_master, or opportunity_signals.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.core.mart.email_mart_feature_scan_parity import (
    run_audit_email_mart_feature_scan_from_argv,
)


def main() -> None:
    raise SystemExit(run_audit_email_mart_feature_scan_from_argv())


if __name__ == "__main__":
    main()
