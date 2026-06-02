"""Deprecated compatibility shim — import from ``read.suppliers_browse`` instead (Streamlit retirement S2)."""

from __future__ import annotations

from origenlab_email_pipeline.read.suppliers_browse import (
    SupplierBrowseFilters,
    build_suppliers_browse_sql,
    fetch_suppliers_browse_df,
    latest_import_batch_id,
    supplier_browse_filter_options,
    supplier_browse_ready,
)

__all__ = [
    "SupplierBrowseFilters",
    "build_suppliers_browse_sql",
    "fetch_suppliers_browse_df",
    "latest_import_batch_id",
    "supplier_browse_filter_options",
    "supplier_browse_ready",
]
