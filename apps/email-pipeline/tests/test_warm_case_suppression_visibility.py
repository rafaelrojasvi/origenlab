"""Promotion status must not hide Banco/DHL warm cases from api.v_warm_case."""

from __future__ import annotations

from origenlab_email_pipeline.warm_case_classification import (
    infer_warm_case_category,
    infer_warm_case_status,
)


def test_banco_factura_status_open_when_suppression_flag() -> None:
    row = {
        "email_id": 1,
        "sender_preview": "serviciodetransferencias@bancochile.cl",
        "subject_preview": "FACTURA 6",
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
        "has_suppression_signal": 1,
        "has_positive_signal": 0,
    }
    cat = infer_warm_case_category(row, enrichment_available=False, include_noise=False)
    assert cat == "client_reply"
    assert infer_warm_case_status(cat, row) == "open"


def test_dhl_import_status_open_when_suppression_flag() -> None:
    row = {
        "email_id": 2,
        "sender_preview": "Monica Silva <monica.silva@dhl.com>",
        "subject_preview": "RE: Solicitud cuenta importación",
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
        "has_suppression_signal": 1,
        "has_positive_signal": 0,
    }
    cat = infer_warm_case_category(row, enrichment_available=False, include_noise=False)
    assert cat == "client_reply"
    assert infer_warm_case_status(cat, row) == "open"
