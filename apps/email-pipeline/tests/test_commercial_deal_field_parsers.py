"""Unit tests for commercial deal field parsers (SERVA/CEAF prototype)."""

from __future__ import annotations

from decimal import Decimal

from origenlab_email_pipeline.commercial.deal_field_parsers import (
    parse_ceaf_oc_number,
    parse_client_invoice_number,
    parse_client_sale_amount_clp,
    parse_serva_customer_code,
    parse_supplier_payment_eur,
    parse_supplier_po_number,
    parse_supplier_proforma_number,
)


def test_parse_serva_customer_code_310471() -> None:
    hit = parse_serva_customer_code(
        "Quotation Request / New adress created for your compagny 310471"
    )
    assert hit is not None
    assert hit.value == "310471"
    assert hit.confidence == "high"


def test_parse_supplier_po_174_26() -> None:
    hit = parse_supplier_po_number("Please confirm PO N°174-26 to SERVA")
    assert hit is not None
    assert hit.value == "174-26"


def test_parse_ceaf_oc_26172() -> None:
    hit = parse_ceaf_oc_number("Remite OC N º 26172 según cotización")
    assert hit is not None
    assert hit.value == "26172"


def test_parse_factura_n6() -> None:
    hit = parse_client_invoice_number("BancoChile FACTURA 6 transferencia CEAF")
    assert hit is not None
    assert hit.value == "6"


def test_parse_eur_218_supplier_payment() -> None:
    hit = parse_supplier_payment_eur("Payment amount EUR 218,00 per Tatiana")
    assert hit is not None
    assert hit.value == Decimal("218.00")


def test_client_sale_unknown_needs_review_not_invented() -> None:
    hit = parse_client_sale_amount_clp("SERVA waiting for DHL account information")
    assert hit.value is None
    assert hit.needs_review is True
    assert hit.confidence == "needs_review"
