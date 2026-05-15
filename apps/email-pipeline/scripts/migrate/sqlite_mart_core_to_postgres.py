#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Writes to Postgres mart.contact_master,
# mart.organization_master, mart.opportunity_signals (+ *_canonical mirrors).
# --replace DELETEs only the selected --tables group. Scratch/staging Postgres only.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Copy SQLite mart core tables into Postgres mart schema (dashboard API Slice 1).

Implementation: origenlab_email_pipeline.mart_core_postgres_migrate
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.mart_core_postgres_migrate import (  # noqa: E402
    ALL_TABLE_SPECS,
    CANONICAL_TABLE_SPECS,
    TABLE_SPECS,
    adapt_jsonb_for_postgres,
    assert_scratch_postgres_target,
    build_parser,
    collect_sqlite_source_counts,
    format_load_progress,
    iso_text_to_datetime,
    load_table,
    main,
    parse_jsonb_python,
    should_refuse_nonempty_targets,
)

# Backward compatibility for tests that import the script module.
_connect_readonly = __import__(
    "origenlab_email_pipeline.mart_core_postgres_migrate",
    fromlist=["connect_sqlite_readonly"],
).connect_sqlite_readonly
_convert_row = __import__(
    "origenlab_email_pipeline.mart_core_postgres_migrate",
    fromlist=["_convert_row"],
)._convert_row
_normalize_iso_z = __import__(
    "origenlab_email_pipeline.mart_core_postgres_migrate",
    fromlist=["_normalize_iso_z"],
)._normalize_iso_z

if __name__ == "__main__":
    raise SystemExit(main())
