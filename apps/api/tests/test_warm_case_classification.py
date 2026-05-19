"""Unit tests for warm-case heuristics."""

from __future__ import annotations

from origenlab_api.services.warm_case_classification import (
    infer_warm_case_category,
    row_to_warm_case_item,
)


def test_classify_bounce() -> None:
    row = {
        "email_id": 1,
        "sender_preview": "mailer-daemon@google.com",
        "subject_preview": "Delivery Status Notification (Failure)",
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
    }
    assert infer_warm_case_category(row, enrichment_available=False, include_noise=False) == "bounce"


def test_classify_quote_sent() -> None:
    row = {
        "email_id": 2,
        "sender_preview": "contacto@origenlab.cl",
        "subject_preview": "Cotización Sonicador",
        "source_file": "gmail:contacto@origenlab.cl/[Gmail]/Enviados",
    }
    assert infer_warm_case_category(row, enrichment_available=False, include_noise=False) == "quote_sent"


def test_row_to_item_has_no_body_fields() -> None:
    row = {
        "email_id": 3,
        "date_iso": "2026-05-19T10:00:00-04:00",
        "sender_preview": "client@udec.cl",
        "subject_preview": "Re: Cotización",
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
        "has_positive_signal": 1,
        "has_suppression_signal": 0,
    }
    item, _ = row_to_warm_case_item(row, enrichment_available=True, include_noise=False)
    assert item.case_id == "gmail-contacto-3"
    assert item.contact_email == "client@udec.cl"
    assert "body" not in item.model_dump()
