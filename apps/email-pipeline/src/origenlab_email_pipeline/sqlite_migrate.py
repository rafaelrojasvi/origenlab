"""Ordered SQLite schema orchestration (no versioned migration framework).

Prefer calling existing init/ensure helpers in a safe sequence. See docs/pipeline/SCHEMA_OWNERSHIP.md.
"""

from __future__ import annotations

import sqlite3
from enum import Enum, auto

from origenlab_email_pipeline.bi_views import refresh_lead_match_summary_view
from origenlab_email_pipeline.commercial_intel_schema import ensure_commercial_intel_tables
from origenlab_email_pipeline.db import init_schema
from origenlab_email_pipeline.lead_accounts_schema import ensure_lead_account_tables
from origenlab_email_pipeline.leads_schema import ensure_leads_tables


class SchemaLayer(Enum):
    ARCHIVE_AND_MART = auto()
    COMMERCIAL_INTEL = auto()
    LEADS = auto()
    LEAD_ACCOUNTS = auto()


_DEFAULT_LAYERS: frozenset[SchemaLayer] = frozenset(
    (SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.LEADS, SchemaLayer.LEAD_ACCOUNTS)
)


def migrate_sqlite_schema(
    conn: sqlite3.Connection,
    *,
    layers: set[SchemaLayer] | None = None,
    leads_backfill_norms: bool = True,
) -> None:
    """Apply schema layers in dependency order.

    Order:
        1. init_schema (archive + mart + pipeline meta + archive/mart migrations)
        2. ensure_commercial_intel_tables
        3. ensure_leads_tables (refresh_view=False)
        4. ensure_lead_account_tables (refresh_view=False)
        5. refresh_lead_match_summary_view once if leads or accounts layer ran

    Args:
        conn: Open SQLite connection (same as other pipeline scripts).
        layers: Subset of SchemaLayer; default = all three.
        leads_backfill_norms: Passed through to ensure_leads_tables.
    """
    active = set(layers) if layers is not None else set(_DEFAULT_LAYERS)

    if SchemaLayer.ARCHIVE_AND_MART in active:
        init_schema(conn)

    if SchemaLayer.COMMERCIAL_INTEL in active:
        ensure_commercial_intel_tables(conn)

    if SchemaLayer.LEADS in active:
        ensure_leads_tables(
            conn,
            backfill_norms=leads_backfill_norms,
            refresh_view=False,
        )

    if SchemaLayer.LEAD_ACCOUNTS in active:
        ensure_lead_account_tables(conn, refresh_view=False)

    if SchemaLayer.LEADS in active or SchemaLayer.LEAD_ACCOUNTS in active:
        refresh_lead_match_summary_view(conn)
