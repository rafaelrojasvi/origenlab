"""Operator product catalogue (SQLite v1, Phase 8B)."""

from origenlab_email_pipeline.catalog.catalog_schema import (
    CATALOG_SCHEMA_VERSION,
    CATALOG_TABLE_NAMES,
    catalog_tables_exist,
    ensure_catalog_tables,
)

__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "CATALOG_TABLE_NAMES",
    "catalog_tables_exist",
    "ensure_catalog_tables",
]
