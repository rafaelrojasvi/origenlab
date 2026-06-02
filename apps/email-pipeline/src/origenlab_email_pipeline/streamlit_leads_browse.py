"""Deprecated compatibility shim — import from ``read.leads_browse`` instead (Streamlit retirement S2)."""

from __future__ import annotations

from origenlab_email_pipeline.read.leads_browse import (
    LeadBrowseFilters,
    build_leads_browse_query,
    fetch_lead_account_rollups_df,
    fetch_leads_browse_df,
    lead_browse_filter_options,
    lead_browse_ready,
)

__all__ = [
    "LeadBrowseFilters",
    "build_leads_browse_query",
    "fetch_lead_account_rollups_df",
    "fetch_leads_browse_df",
    "lead_browse_filter_options",
    "lead_browse_ready",
]
