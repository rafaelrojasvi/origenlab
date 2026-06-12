"""Unit tests for mirror lead prospect contact_scope filtering."""

from __future__ import annotations

from origenlab_email_pipeline.postgres_dashboard_api.lead_intel import (
    CONTACT_SCOPES,
    _PUBLIC_EMAIL_DOMAINS,
    contact_scope_sql_clause,
    contact_scope_sql_params,
)


def test_contact_scope_sql_clause_known_values() -> None:
    assert CONTACT_SCOPES == frozenset(
        {"contacted", "followup", "active", "deepsearch", "net_new", "blocked"}
    )
    assert contact_scope_sql_clause("unknown") is None


def test_contact_scope_contacted_includes_outreach_exists() -> None:
    clause = contact_scope_sql_clause("contacted", include_outreach=True)
    assert clause is not None
    assert "source_type IN" in clause
    assert "outbound.outreach_contact_state" in clause
    params = contact_scope_sql_params("contacted", include_outreach=True)
    assert params[:4] == [
        "gmail_historico",
        "followup_antiguo",
        "caso_activo",
        "same_domain_contacted_review",
    ]
    assert params[4:6] == ["contacted", "replied"]
    assert params[6:] == list(_PUBLIC_EMAIL_DOMAINS)


def test_contact_scope_without_outreach_table() -> None:
    clause = contact_scope_sql_clause("contacted", include_outreach=False)
    assert clause is not None
    assert "outbound.outreach_contact_state" not in clause
    assert contact_scope_sql_params("contacted", include_outreach=False) == [
        "gmail_historico",
        "followup_antiguo",
        "caso_activo",
        "same_domain_contacted_review",
    ]


def test_contact_scope_followup_and_active_outreach_params() -> None:
    followup_clause = contact_scope_sql_clause("followup", include_outreach=True)
    assert followup_clause is not None
    assert "outbound.outreach_contact_state" in followup_clause
    assert contact_scope_sql_params("followup", include_outreach=True) == [
        "contacted",
        *list(_PUBLIC_EMAIL_DOMAINS),
    ]

    active_clause = contact_scope_sql_clause("active", include_outreach=True)
    assert active_clause is not None
    assert "outbound.outreach_contact_state" in active_clause
    assert contact_scope_sql_params("active", include_outreach=True) == [
        "caso_activo",
        "replied",
        *list(_PUBLIC_EMAIL_DOMAINS),
    ]


def test_contact_scope_net_new_excludes_outreach_contacted() -> None:
    clause = contact_scope_sql_clause("net_new", include_outreach=True)
    assert clause is not None
    assert "NOT EXISTS" in clause.upper()
    assert "outbound.outreach_contact_state" in clause
    assert contact_scope_sql_params("net_new", include_outreach=True) == [
        "contacted",
        "replied",
        *list(_PUBLIC_EMAIL_DOMAINS),
    ]


def test_contact_scope_deepsearch_and_blocked_unchanged() -> None:
    assert contact_scope_sql_clause("deepsearch") == "source_type = %s"
    assert contact_scope_sql_params("deepsearch") == ["deepsearch"]
    assert contact_scope_sql_clause("blocked") == "is_blocked = TRUE"
    assert contact_scope_sql_params("blocked") == []
