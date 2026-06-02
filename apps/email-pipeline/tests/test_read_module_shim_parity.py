"""Streamlit retirement S2: neutral read modules and shim re-export identity."""

from __future__ import annotations

import origenlab_email_pipeline.operator_copy_es as operator_copy
import origenlab_email_pipeline.read.leads_browse as leads_browse
import origenlab_email_pipeline.read.suppliers_browse as suppliers_browse
import origenlab_email_pipeline.read.today_workspace as today_workspace
import origenlab_email_pipeline.streamlit_borrador_support as borrador_shim
import origenlab_email_pipeline.streamlit_leads_browse as leads_shim
import origenlab_email_pipeline.streamlit_prioridad_copy as copy_shim
import origenlab_email_pipeline.streamlit_suppliers_browse as suppliers_shim
import origenlab_email_pipeline.streamlit_today_workspace as today_shim
import origenlab_email_pipeline.tatiana_copilot.borrador_support as borrador_support


def test_leads_browse_shim_reexports() -> None:
    for name in leads_shim.__all__:
        assert getattr(leads_shim, name) is getattr(leads_browse, name)


def test_suppliers_browse_shim_reexports() -> None:
    for name in suppliers_shim.__all__:
        assert getattr(suppliers_shim, name) is getattr(suppliers_browse, name)


def test_today_workspace_shim_reexports() -> None:
    for name in today_shim.__all__:
        assert getattr(today_shim, name) is getattr(today_workspace, name)


def test_operator_copy_shim_reexports() -> None:
    for name in copy_shim.__all__:
        assert getattr(copy_shim, name) is getattr(operator_copy, name)


def test_borrador_support_shim_reexports() -> None:
    for name in borrador_shim.__all__:
        assert getattr(borrador_shim, name) is getattr(borrador_support, name)
