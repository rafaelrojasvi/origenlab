"""Deprecated compatibility shim — import from ``read.today_workspace`` instead (Streamlit retirement S2)."""

from __future__ import annotations

from origenlab_email_pipeline.read.today_workspace import (
    SOURCE_LABEL_ES,
    TIER_CANDIDATO_NEEDS_REVIEW,
    TIER_CASO_SENAL_POSITIVA,
    TIER_CUENTA_DORMIDA,
    TIER_LABELS_ES,
    TIER_LEAD_SIN_NEXT_ACTION,
    TodayWorkspaceRow,
    TodayWorkspaceSpec,
    apply_today_row_handoff,
    gather_today_workspace_rows,
    sort_today_rows,
    source_label_es,
)

__all__ = [
    "SOURCE_LABEL_ES",
    "TIER_CANDIDATO_NEEDS_REVIEW",
    "TIER_CASO_SENAL_POSITIVA",
    "TIER_CUENTA_DORMIDA",
    "TIER_LABELS_ES",
    "TIER_LEAD_SIN_NEXT_ACTION",
    "TodayWorkspaceRow",
    "TodayWorkspaceSpec",
    "apply_today_row_handoff",
    "gather_today_workspace_rows",
    "sort_today_rows",
    "source_label_es",
]
