"""Characterization tests for postgres_dashboard_api/schemas.py (API-3 mirror contracts)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel

import origenlab_email_pipeline.postgres_dashboard_api as pg_api
import origenlab_email_pipeline.postgres_dashboard_api.schemas as schemas

_SCHEMAS_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "origenlab_email_pipeline"
    / "postgres_dashboard_api"
    / "schemas.py"
)

# Re-exported by postgres_dashboard_api.__init__ (apps/api mirror stack imports these paths).
_PACKAGE_EXPORTED_MODELS = (
    "ClassificationActionGroup",
    "ClassificationActionsResponse",
    "ClassificationEmailRow",
    "ClassificationRecentResponse",
    "ClassificationSummaryResponse",
    "CommercialDealDetailResponse",
    "CommercialDealRow",
    "CommercialDealsListResponse",
    "CommercialPurchaseEventDetailResponse",
    "CommercialPurchaseEventItemRow",
    "CommercialPurchaseEventRow",
    "CommercialPurchaseEventsListResponse",
    "DashboardSummaryResponse",
    "DashboardSyncMetaResponse",
    "DependencyStatus",
    "EmailSuppressionRow",
    "HealthDependenciesResponse",
    "OutreachContactStateRow",
    "OutboundReadinessResponse",
    "PaginatedEmailSuppressionsResponse",
    "PaginatedOutreachStateResponse",
)

# Direct imports from apps/api mirror routes (response_model contracts).
_API_MIRROR_RESPONSE_MODELS = (
    "DashboardSummaryResponse",
    "DashboardSyncMetaResponse",
    "HealthDependenciesResponse",
    "ClassificationSummaryResponse",
    "ClassificationRecentResponse",
    "ClassificationActionsResponse",
    "PaginatedContactsResponse",
    "PaginatedOrganizationsResponse",
    "PaginatedEmailSuppressionsResponse",
    "PaginatedOutreachStateResponse",
    "OutboundReadinessResponse",
    "CommercialPurchaseEventsListResponse",
    "CommercialPurchaseEventDetailResponse",
    "CommercialDealsListResponse",
    "CommercialDealDetailResponse",
    "CatalogProductsListResponse",
    "CatalogProductDetailResponse",
    "LeadProspectsListResponse",
    "LeadProspectDetailResponse",
    "LeadResearchSummaryResponse",
)

_ALL_SCHEMA_MODELS = tuple(
    name
    for name, obj in vars(schemas).items()
    if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel
)


def _required_field_names(model: type[BaseModel]) -> frozenset[str]:
    return frozenset(
        name
        for name, field in model.model_fields.items()
        if field.is_required()
    )


def _dump_keys(model: type[BaseModel], payload: dict[str, Any]) -> frozenset[str]:
    return frozenset(model.model_validate(payload).model_dump().keys())


# --- Module constants & disclaimers ---------------------------------------------------


def test_postgres_mirror_note_spanish_operator_wording() -> None:
    assert "Espejo Postgres" in schemas.POSTGRES_MIRROR_NOTE
    assert "SQLite" in schemas.POSTGRES_MIRROR_NOTE
    assert "Gmail" in schemas.POSTGRES_MIRROR_NOTE


def test_lead_research_disclaimer_sentence_break_guard() -> None:
    assert "OrigenLab. Revisión" in schemas.LEAD_RESEARCH_DISCLAIMER
    assert "OrigenLab.Revisión" not in schemas.LEAD_RESEARCH_DISCLAIMER


def test_prepare_lead_research_disclaimer_repairs_joined_origenlab() -> None:
    broken = "Prospectos desde OrigenLab.Revisión humana requerida."
    fixed = schemas.prepare_lead_research_disclaimer(broken)
    assert isinstance(fixed, str)
    assert "OrigenLab. Revisión" in fixed


def test_disclaimer_constants_are_non_empty_strings() -> None:
    for name in (
        "COMMERCIAL_PURCHASE_DISCLAIMER",
        "COMMERCIAL_DEAL_DISCLAIMER",
        "CATALOG_DISCLAIMER",
        "LEAD_RESEARCH_DISCLAIMER",
    ):
        value = getattr(schemas, name)
        assert isinstance(value, str)
        assert len(value) > 20


# --- Exported model registry ---------------------------------------------------------


@pytest.mark.parametrize("name", _PACKAGE_EXPORTED_MODELS)
def test_package_reexports_schema_models(name: str) -> None:
    assert hasattr(pg_api, name)
    assert getattr(pg_api, name) is getattr(schemas, name)


@pytest.mark.parametrize("name", _API_MIRROR_RESPONSE_MODELS)
def test_api_mirror_response_models_exist_in_schemas_module(name: str) -> None:
    assert hasattr(schemas, name), f"apps/api mirror route expects {name}"


def test_all_schema_models_are_base_model_subclasses() -> None:
    assert len(_ALL_SCHEMA_MODELS) >= 30
    for name in _ALL_SCHEMA_MODELS:
        cls = getattr(schemas, name)
        assert issubclass(cls, BaseModel), name


def test_schemas_module_has_no_streamlit_references() -> None:
    text = _SCHEMAS_PATH.read_text(encoding="utf-8").lower()
    assert "streamlit" not in text
    tree = ast.parse(_SCHEMAS_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "streamlit" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            assert "streamlit" not in (node.module or "").lower()


# --- Dashboard / sync meta (operator Today-adjacent counts live in lead summary) -----


def test_dashboard_summary_defaults_and_literals() -> None:
    row = schemas.DashboardSummaryResponse()
    dump = row.model_dump()
    assert dump["data_source"] == "postgres_mirror"
    assert dump["eventually_consistent"] is True
    assert dump["scope"] == "canonical"
    assert dump["scope_available"] is True
    assert dump["contact_count"] == 0
    assert dump["opportunity_signal_count"] == 0
    assert dump["tables"] == {}
    assert dump["archive_mirror_counts"] == {}


def test_dashboard_summary_scope_literal_values() -> None:
    field = schemas.DashboardSummaryResponse.model_fields["scope"]
    assert get_args(field.annotation) == ("canonical", "archive")


def test_dashboard_sync_meta_defaults_and_postgres_note() -> None:
    meta = schemas.DashboardSyncMetaResponse()
    dump = meta.model_dump()
    assert dump["status"] == "no_rows"
    assert dump["postgres_mirror_note"] == schemas.POSTGRES_MIRROR_NOTE
    assert dump["canonical_opportunity_signal_count"] == 0
    assert dump["table_available"] is False


def test_dashboard_sync_meta_status_literal_values() -> None:
    field = schemas.DashboardSyncMetaResponse.model_fields["status"]
    assert set(get_args(field.annotation)) == {
        "missing_table",
        "no_rows",
        "success",
        "failed",
        "dry_run",
        "unknown",
    }


# --- Classification queue (recent / actions) -----------------------------------------


def test_classification_summary_spanish_disclaimer_and_status_default() -> None:
    resp = schemas.ClassificationSummaryResponse()
    assert "Gmail canónico" in resp.disclaimer
    assert "contacto@origenlab.cl" in resp.disclaimer
    assert resp.scope == "canonical"
    assert resp.status == "no_rows"
    assert resp.table_available is False


def test_classification_summary_status_literal_values() -> None:
    field = schemas.ClassificationSummaryResponse.model_fields["status"]
    assert get_args(field.annotation) == ("missing_table", "no_rows", "ok")


def test_classification_email_row_required_fields() -> None:
    required = _required_field_names(schemas.ClassificationEmailRow)
    assert required == frozenset(
        {
            "email_id",
            "predicted_label",
            "confidence",
            "recommended_action",
            "etiqueta_ui",
        }
    )


def test_classification_recent_response_default_pagination() -> None:
    resp = schemas.ClassificationRecentResponse()
    assert resp.limit == 20
    assert resp.items == []
    assert resp.total == 0
    assert resp.scope == "canonical"


def test_classification_actions_response_spanish_disclaimer() -> None:
    resp = schemas.ClassificationActionsResponse()
    assert "dashboard" in resp.disclaimer.lower()
    assert resp.groups == []


def test_classification_email_row_model_dump_shape() -> None:
    keys = _dump_keys(
        schemas.ClassificationEmailRow,
        {
            "email_id": 42,
            "predicted_label": "cliente",
            "confidence": "alta",
            "recommended_action": "revisar",
            "etiqueta_ui": "Cliente",
        },
    )
    assert "ambiguous" in keys
    assert "evidence" in keys
    assert keys >= _required_field_names(schemas.ClassificationEmailRow)


# --- Outbound sidecar rows & readiness -----------------------------------------------


def test_email_suppression_row_required_vs_optional() -> None:
    required = _required_field_names(schemas.EmailSuppressionRow)
    assert required == frozenset({"email", "suppression_reason_code"})
    row = schemas.EmailSuppressionRow.model_validate(
        {"email": "a@b.cl", "suppression_reason_code": "bounce"}
    )
    assert row.suppression_reason_text is None


def test_paginated_suppressions_envelope_shape() -> None:
    keys = _dump_keys(
        schemas.PaginatedEmailSuppressionsResponse,
        {
            "items": [],
            "total": 0,
            "limit": 50,
            "offset": 0,
        },
    )
    assert keys == frozenset({"items", "total", "limit", "offset", "table_available"})


def test_outreach_contact_state_row_requires_norm_and_state() -> None:
    assert _required_field_names(schemas.OutreachContactStateRow) == frozenset(
        {"contact_email_norm", "state"}
    )


def test_outbound_readiness_verdict_literal_values() -> None:
    field = schemas.OutboundReadinessResponse.model_fields["verdict"]
    assert get_args(field.annotation) == (
        "ready",
        "ready_with_warnings",
        "not_ready",
        "unknown",
    )


def test_outbound_readiness_defaults_mirror_metadata() -> None:
    resp = schemas.OutboundReadinessResponse(verdict="unknown")
    assert resp.data_source == "postgres_mirror"
    assert resp.eventually_consistent is True
    assert "Postgres mirror" in resp.disclaimer
    assert resp.warnings == []


# --- Commercial purchase & deals -----------------------------------------------------


def test_commercial_purchase_event_row_required_fields() -> None:
    required = _required_field_names(schemas.CommercialPurchaseEventRow)
    assert "buyer_org_name" in required
    assert "purchase_status" in required
    assert "oc_number" in required


def test_commercial_purchase_list_carries_shared_disclaimer() -> None:
    resp = schemas.CommercialPurchaseEventsListResponse()
    assert resp.disclaimer == schemas.COMMERCIAL_PURCHASE_DISCLAIMER
    assert resp.limit == 20


def test_commercial_deal_row_excludes_forbidden_private_fields() -> None:
    fields = set(schemas.CommercialDealRow.model_fields.keys())
    assert "margin_notes" not in fields
    assert "client_contact_email" not in fields


def test_commercial_deals_list_response_mirror_flags() -> None:
    resp = schemas.CommercialDealsListResponse()
    assert resp.data_source == "postgres_mirror"
    assert resp.read_only is True
    assert resp.disclaimer == schemas.COMMERCIAL_DEAL_DISCLAIMER


# --- Catalog mirror ------------------------------------------------------------------


def test_catalog_products_list_response_defaults() -> None:
    resp = schemas.CatalogProductsListResponse()
    assert resp.limit == 50
    assert resp.read_only is True
    assert resp.disclaimer == schemas.CATALOG_DISCLAIMER


def test_catalog_product_list_item_requires_keys() -> None:
    assert _required_field_names(schemas.CatalogProductListItem) == frozenset(
        {"product_key", "display_name", "product_kind", "confidence"}
    )


def test_catalog_disclaimer_validator_repairs_legacy_broken_prose_join() -> None:
    resp = schemas.CatalogProductsListResponse.model_validate(
        {
            "table_available": True,
            "items": [],
            "total": 0,
            "disclaimer": "espejoPostgres redactado",
        }
    )
    assert "espejo Postgres" in resp.disclaimer


# --- Lead research (operator queue buckets: caso_activo, etc.) -----------------------


def test_lead_research_summary_operator_bucket_fields() -> None:
    """Mirror lead-intel summary exposes caso/follow-up buckets (not Streamlit Today UI)."""
    fields = set(schemas.LeadResearchSummaryResponse.model_fields.keys())
    for name in (
        "caso_activo",
        "followup_antiguo",
        "gmail_historico",
        "net_new_safe",
        "review_count",
        "blocked_count",
    ):
        assert name in fields


def test_lead_prospect_list_item_required_classification_fields() -> None:
    assert _required_field_names(schemas.LeadProspectListItem) == frozenset(
        {"prospect_key", "organization_name", "classification", "status"}
    )


def test_lead_prospects_list_disclaimer_uses_prepare_helper() -> None:
    resp = schemas.LeadProspectsListResponse.model_validate(
        {
            "table_available": True,
            "items": [],
            "total": 0,
            "disclaimer": "Texto OrigenLab.Revisión de prueba.",
        }
    )
    assert "OrigenLab. Revisión" in resp.disclaimer


def test_lead_prospect_detail_response_nested_defaults() -> None:
    resp = schemas.LeadProspectDetailResponse()
    assert resp.prospect is None
    assert resp.evidence == []
    assert resp.block_reasons == []
    assert resp.recommendation is None
    assert resp.read_only is True


def test_lead_prospect_detail_response_full_payload_roundtrip() -> None:
    payload = {
        "table_available": True,
        "prospect": {
            "prospect_key": "p-1",
            "organization_name": "Hospital Regional",
            "classification": "review",
            "status": "open",
        },
        "evidence": [{"evidence_kind": "public_url", "evidence_url": "https://example.cl"}],
        "recommendation": {
            "recommended_next_action": "Revisar cotización",
            "suggested_subject": "Equipos de laboratorio",
        },
        "block_reasons": [{"reason_code": "duplicate_domain"}],
    }
    resp = schemas.LeadProspectDetailResponse.model_validate(payload)
    dump = resp.model_dump()
    assert dump["prospect"]["organization_name"] == "Hospital Regional"
    assert dump["evidence"][0]["evidence_kind"] == "public_url"
    assert dump["block_reasons"][0]["reason_code"] == "duplicate_domain"


# --- Mart contacts / orgs pagination -------------------------------------------------


def test_contact_and_org_pagination_scope_defaults() -> None:
    for cls in (schemas.PaginatedContactsResponse, schemas.PaginatedOrganizationsResponse):
        resp = cls.model_validate({"items": [], "total": 0, "limit": 25, "offset": 0})
        assert resp.scope == "canonical"
        assert resp.scope_available is True
        assert resp.table_available is True


def test_contact_row_requires_email() -> None:
    assert _required_field_names(schemas.ContactRow) == frozenset({"email"})


# --- Health dependencies -------------------------------------------------------------


def test_health_dependencies_status_literal() -> None:
    dep_field = schemas.DependencyStatus.model_fields["status"]
    assert get_args(dep_field.annotation) == ("ok", "error", "skipped")
    health_field = schemas.HealthDependenciesResponse.model_fields["status"]
    assert get_args(health_field.annotation) == ("ok", "degraded", "error")


def test_health_dependencies_note_mentions_sqlite_authority() -> None:
    resp = schemas.HealthDependenciesResponse(status="ok", dependencies=[])
    assert "SQLite" in resp.note
