"""Streamlit retirement Phase 5E: neutral read modules remain; S2 shims removed."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "src" / "origenlab_email_pipeline"

_REMOVED_SHIMS = (
    "streamlit_leads_browse",
    "streamlit_suppliers_browse",
    "streamlit_today_workspace",
    "streamlit_borrador_support",
    "streamlit_prioridad_copy",
)


@pytest.mark.parametrize("module_name", _REMOVED_SHIMS)
def test_phase5e_streamlit_shim_modules_removed(module_name: str) -> None:
    assert not (PKG / f"{module_name}.py").is_file(), module_name


def test_leads_browse_neutral_exports() -> None:
    mod = import_module("origenlab_email_pipeline.read.leads_browse")
    for name in (
        "LeadBrowseFilters",
        "build_leads_browse_query",
        "fetch_lead_account_rollups_df",
        "fetch_leads_browse_df",
        "lead_browse_filter_options",
        "lead_browse_ready",
    ):
        assert callable(getattr(mod, name))


def test_suppliers_browse_neutral_exports() -> None:
    mod = import_module("origenlab_email_pipeline.read.suppliers_browse")
    for name in (
        "SupplierBrowseFilters",
        "build_suppliers_browse_sql",
        "fetch_suppliers_browse_df",
        "supplier_browse_filter_options",
        "supplier_browse_ready",
    ):
        assert callable(getattr(mod, name))


def test_today_workspace_neutral_exports() -> None:
    mod = import_module("origenlab_email_pipeline.read.today_workspace")
    for name in mod.__all__:
        assert hasattr(mod, name)


def test_operator_copy_neutral_exports() -> None:
    mod = import_module("origenlab_email_pipeline.operator_copy_es")
    for name in mod.__all__:
        assert hasattr(mod, name)


def test_borrador_support_neutral_exports() -> None:
    mod = import_module("origenlab_email_pipeline.tatiana_copilot.borrador_support")
    for name in mod.__all__:
        assert hasattr(mod, name)
