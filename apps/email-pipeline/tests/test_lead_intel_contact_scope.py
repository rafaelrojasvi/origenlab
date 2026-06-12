"""Unit tests for mirror lead prospect contact_scope filtering."""

from __future__ import annotations

from origenlab_email_pipeline.postgres_dashboard_api.lead_intel import (
    CONTACT_SCOPES,
    contact_scope_sql_clause,
    contact_scope_sql_params,
)


def test_contact_scope_sql_clause_known_values() -> None:
    assert CONTACT_SCOPES == frozenset(
        {"contacted", "followup", "active", "deepsearch", "net_new", "blocked"}
    )
    assert contact_scope_sql_clause("contacted") and "source_type IN" in contact_scope_sql_clause("contacted") or ""
    assert contact_scope_sql_clause("followup")
    assert contact_scope_sql_params("active") == ["caso_activo"]
    assert contact_scope_sql_params("deepsearch") == ["deepsearch"]
    assert contact_scope_sql_params("contacted") == [
        "gmail_historico",
        "followup_antiguo",
        "caso_activo",
        "same_domain_contacted_review",
    ]
    assert contact_scope_sql_clause("unknown") is None
