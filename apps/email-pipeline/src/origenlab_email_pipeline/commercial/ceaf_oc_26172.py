"""Structured CEAF OC 26172 payload (operator-confirmed; not React-hardcoded)."""

from __future__ import annotations

from typing import Any

CEAF_OC_NUMBER = "26172"
CEAF_BUYER_DOMAIN = "ceaf.cl"
CEAF_SUBJECT_FRAGMENT = "Remite OC N º 26172"


def ceaf_oc_26172_event_fields() -> dict[str, Any]:
    """Event row fields excluding source email linkage (filled at promotion time)."""
    return {
        "buyer_org_name": "Centro de Estudios Avanzados en Fruticultura CEAF",
        "buyer_rut": "65.088.704-2",
        "buyer_contact_name": "Carlos Garay Sotelo",
        "buyer_contact_role": "Subdirector de Gestión Corporativa CEAF",
        "buyer_contact_email": "cgaray@ceaf.cl",
        "buyer_domain": CEAF_BUYER_DOMAIN,
        "purchase_status": "purchase_order_received",
        "oc_number": CEAF_OC_NUMBER,
        "oc_date": "2026-05-14",
        "quote_number": "011728A-26",
        "quote_date": "2026-04-30",
        "project_name": "ANID",
        "project_code": "R23F0002",
        "project_responsible": "Verónica Guajardo",
        "associated_line": "Mejoramiento Genético",
        "net_amount_clp": 1_260_000,
        "iva_amount_clp": 239_400,
        "gross_amount_clp": 1_499_400,
        "currency": "CLP",
        "payment_terms": "Crédito",
        "delivery_address": (
            "Camino Las Parcelas Nº 882, Sector Los Choapinos, Rengo"
        ),
        "invoice_email": "FRANCISCAGONZALEZ@CEAF.CL",
        "invoice_cc_email": "VLAZO@CEAF.CL",
        "dispatch_requested": 1,
        "invoice_requested": 1,
        "bank_details_requested": 1,
        "commercial_summary": (
            "CEAF remite Orden de Compra N.º 26172 según cotización 011728A-26. "
            "Solicitan confirmar fecha de despacho, enviar factura con código de "
            "proyecto ANID R23F0002 y datos bancarios para transferencia."
        ),
        "confidence": "operator_confirmed",
    }


def ceaf_oc_26172_line_items() -> list[dict[str, Any]]:
    return [
        {
            "line_number": 1,
            "ref_code": "4250001",
            "product_name": "BlueSlick™ 250 ml",
            "brand": "SERVA",
            "quantity": None,
            "net_amount_clp": 695_000,
            "evidence_source": "oc_attachment",
        },
        {
            "line_number": 2,
            "ref_code": "3593002",
            "product_name": "N,N,N',N'-Tetramethyl-ethylenediamine, 25 ml",
            "brand": "SERVA",
            "quantity": None,
            "net_amount_clp": 545_000,
            "evidence_source": "oc_attachment",
        },
        {
            "line_number": 3,
            "ref_code": "E01",
            "product_name": "Envío",
            "brand": None,
            "quantity": None,
            "net_amount_clp": 20_000,
            "evidence_source": "oc_attachment",
        },
    ]


def ceaf_oc_26172_expected_attachment_filenames() -> tuple[str, str]:
    return (
        "OC N º 26172.pdf",
        "CN011728A-Verónica Guajardo – Tatiana Vivanco.pdf",
    )
