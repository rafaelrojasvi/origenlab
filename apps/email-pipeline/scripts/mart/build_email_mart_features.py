#!/usr/bin/env python3
"""Backfill or profile precomputed email_mart_features from SQLite emails.

Dry-run by default. Pass ``--apply`` to write missing/stale feature rows.
Not wired into standalone build-mart default path; daily-core --apply runs missing-only --apply before feature-backed mart rebuild.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.core.mart.build_email_mart_features_cli import (
    run_build_email_mart_features_from_argv,
)


def main() -> None:
    raise SystemExit(run_build_email_mart_features_from_argv())


if __name__ == "__main__":
    main()
