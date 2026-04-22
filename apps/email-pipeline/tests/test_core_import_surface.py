"""Smoke tests for ``origenlab_email_pipeline.core`` re-export import surface (Stage 2A).

No DB mutations, no network, no email sending — attribute checks and imports only.
"""

from __future__ import annotations


def test_core_infra_imports() -> None:
    from origenlab_email_pipeline.core import config
    from origenlab_email_pipeline.core import db
    from origenlab_email_pipeline.core import sqlite_migrate

    assert config.__name__ == "origenlab_email_pipeline.core.config"
    assert db.__name__ == "origenlab_email_pipeline.core.db"
    assert sqlite_migrate.__name__ == "origenlab_email_pipeline.core.sqlite_migrate"


def test_core_outbound_imports() -> None:
    from origenlab_email_pipeline.core.outbound import candidate_export_gate
    from origenlab_email_pipeline.core.outbound import contact_domain_suppression
    from origenlab_email_pipeline.core.outbound import contact_email_suppression
    from origenlab_email_pipeline.core.outbound import csv_contracts
    from origenlab_email_pipeline.core.outbound import manual_html_outreach_batch
    from origenlab_email_pipeline.core.outbound import marketing_contact_noise
    from origenlab_email_pipeline.core.outbound import marketing_export_context
    from origenlab_email_pipeline.core.outbound import marketing_supplier_domains
    from origenlab_email_pipeline.core.outbound import merge_marketing_contact_csvs
    from origenlab_email_pipeline.core.outbound import next_marketing_queue
    from origenlab_email_pipeline.core.outbound import outbound_core
    from origenlab_email_pipeline.core.outbound import outbound_sent_preflight
    from origenlab_email_pipeline.core.outbound import outreach_contact_state

    for mod in (
        candidate_export_gate,
        csv_contracts,
        outbound_core,
        outbound_sent_preflight,
        outreach_contact_state,
        contact_email_suppression,
        contact_domain_suppression,
        marketing_export_context,
        marketing_contact_noise,
        marketing_supplier_domains,
        merge_marketing_contact_csvs,
        next_marketing_queue,
        manual_html_outreach_batch,
    ):
        assert mod.__name__.startswith("origenlab_email_pipeline.core.outbound.")


def test_core_gmail_imports() -> None:
    from origenlab_email_pipeline.core.gmail import contacto_gmail_source
    from origenlab_email_pipeline.core.gmail import gmail_send
    from origenlab_email_pipeline.core.gmail import gmail_workspace_oauth

    assert gmail_workspace_oauth.__name__ == "origenlab_email_pipeline.core.gmail.gmail_workspace_oauth"
    assert gmail_send.__name__ == "origenlab_email_pipeline.core.gmail.gmail_send"
    assert contacto_gmail_source.__name__ == "origenlab_email_pipeline.core.gmail.contacto_gmail_source"


def test_core_mart_and_supplier_imports() -> None:
    from origenlab_email_pipeline.core.mart import business_mart
    from origenlab_email_pipeline.core.mart import business_mart_schema
    from origenlab_email_pipeline.core.suppliers import supplier_schema
    from origenlab_email_pipeline.core.suppliers import supplier_workbook

    assert business_mart.__name__ == "origenlab_email_pipeline.core.mart.business_mart"
    assert business_mart_schema.__name__ == "origenlab_email_pipeline.core.mart.business_mart_schema"
    assert supplier_schema.__name__ == "origenlab_email_pipeline.core.suppliers.supplier_schema"
    assert supplier_workbook.__name__ == "origenlab_email_pipeline.core.suppliers.supplier_workbook"


def test_core_leads_package_importable() -> None:
    import origenlab_email_pipeline.core.leads as leads_core

    assert leads_core.__name__ == "origenlab_email_pipeline.core.leads"


def test_core_candidate_export_gate_reexports_evaluate_export_eligibility() -> None:
    from origenlab_email_pipeline.core.outbound.candidate_export_gate import evaluate_export_eligibility

    assert callable(evaluate_export_eligibility)


def test_core_csv_contracts_reexports_public_helpers() -> None:
    from origenlab_email_pipeline.core.outbound import csv_contracts

    assert hasattr(csv_contracts, "has_required_columns")
    assert hasattr(csv_contracts, "validate_email_syntax")
    assert callable(csv_contracts.has_required_columns)
    assert callable(csv_contracts.validate_email_syntax)


def test_core_gmail_send_exposes_gmail_api_send_message_without_invoking() -> None:
    from origenlab_email_pipeline.core.gmail import gmail_send

    assert hasattr(gmail_send, "gmail_api_send_message")
    assert callable(gmail_send.gmail_api_send_message)
