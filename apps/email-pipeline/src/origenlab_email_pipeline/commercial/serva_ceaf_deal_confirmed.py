"""Operator-confirmed SERVA → CEAF deal facts (2026-05-26). Not inferred from email alone."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

DEAL_KEY = "serva-ceaf-oc-26172-po-174-26"
DEAL_STATUS = "paid_by_client__supplier_payment_sent__logistics_pending"
FREIGHT_STATUS = "dhl_account_or_external_freight"
RECONCILIATION_STATUS = "reconciled_excluding_supplier_freight"

# Amounts (operator-confirmed)
CLIENT_PAYMENT_RECEIVED_CLP = 1_499_400
CLIENT_SALE_AMOUNT_GROSS_CLP = 1_499_400
CLIENT_SALE_AMOUNT_NET_CLP = 1_260_000
CLIENT_IVA_AMOUNT_CLP = 239_400
CLIENT_IVA_RATE = Decimal("0.19")
CLIENT_PO_NUMBER = "26172"
CLIENT_INVOICE_NUMBER = "6"
SUPPLIER_CUSTOMER_CODE = "310471"
SUPPLIER_PO_NUMBER = "174-26"
SUPPLIER_PROFORMA_NUMBER = "A2602545"
SUPPLIER_PROFORMA_DATE = "2026-05-14"

SUPPLIER_INVOICE_TOTAL_EUR = Decimal("363.00")
SUPPLIER_PRODUCT_COST_EUR = Decimal("148.00")  # BlueSlick 117 + TEMED 31
SUPPLIER_HANDLING_COST_EUR = Decimal("70.00")  # 25 + 45
SUPPLIER_FREIGHT_QUOTED_EUR = Decimal("145.00")
SUPPLIER_AMOUNT_PAID_EUR = Decimal("218.00")
WISE_TOTAL_PAID_USD = Decimal("268.47")
SUPPLIER_PAYMENT_TRANSFER_ID = "2152655677"
SUPPLIER_PAYMENT_METHOD = "Wise"

CLIENT_PAYMENT_AT = "2026-05-22T11:34:00-04:00"
CLIENT_PAYMENT_SUBJECT = "FACTURA 6"
# Full ID kept for operator preview only; public export must redact.
CLIENT_PAYMENT_OPERATION_ID = "INT_EMP2605221134124589096100"

WISE_FUNDED_AT = "2026-05-25T14:50:24-04:00"
WISE_PAID_OUT_DATE = "2026-05-25"
WISE_FUNDS_AVAILABLE_DATE = "2026-05-30"

DELIVERY_ESTIMATE_WEEKS = "2_to_3_weeks"
INVOICE_SENT_TO_CLIENT_DATE = "2026-05-14"


def _rate_field(value: Decimal | float, *, source: str) -> dict[str, Any]:
    return {
        "value": float(value),
        "confidence": "operator_confirmed",
        "source": source,
        "needs_review": False,
    }


def _money_field(value: Decimal | int, *, currency: str, source: str) -> dict[str, Any]:
    if isinstance(value, int):
        display: str | int = value
    else:
        display = format(value, "f")
    return {
        "value": display,
        "currency": currency,
        "confidence": "operator_confirmed",
        "source": source,
        "needs_review": False,
    }


def build_confirmed_fields() -> dict[str, dict[str, Any]]:
    return {
        "supplier_customer_code": {
            "value": SUPPLIER_CUSTOMER_CODE,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
        "supplier_po_number": {
            "value": SUPPLIER_PO_NUMBER,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
        "client_po_number": {
            "value": CLIENT_PO_NUMBER,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
        "client_invoice_number": {
            "value": CLIENT_INVOICE_NUMBER,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
        "supplier_invoice_proforma": {
            "value": SUPPLIER_PROFORMA_NUMBER,
            "proforma_date": SUPPLIER_PROFORMA_DATE,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
        "client_payment_received_clp": _money_field(
            CLIENT_PAYMENT_RECEIVED_CLP,
            currency="CLP",
            source="operator_confirmed:bancochile_factura_6",
        ),
        "client_sale_amount_gross_clp": _money_field(
            CLIENT_SALE_AMOUNT_GROSS_CLP,
            currency="CLP",
            source="operator_confirmed:ceaf_quotation_plus_iva_matches_factura_6",
        ),
        "client_sale_amount_net_clp": _money_field(
            CLIENT_SALE_AMOUNT_NET_CLP,
            currency="CLP",
            source="operator_confirmed:ceaf_quotation_subtotal_ex_iva",
        ),
        "client_iva_amount_clp": _money_field(
            CLIENT_IVA_AMOUNT_CLP,
            currency="CLP",
            source="operator_confirmed:19pct_iva_on_net_1260000",
        ),
        "client_iva_rate": _rate_field(
            CLIENT_IVA_RATE,
            source="operator_confirmed:chilean_iva_19pct",
        ),
        "supplier_invoice_total_eur": _money_field(
            SUPPLIER_INVOICE_TOTAL_EUR,
            currency="EUR",
            source="operator_confirmed:serva_proforma_a2602545",
        ),
        "supplier_product_cost_eur": _money_field(
            SUPPLIER_PRODUCT_COST_EUR,
            currency="EUR",
            source="operator_confirmed:proforma_lines_blueslick_temed",
        ),
        "supplier_handling_cost_eur": _money_field(
            SUPPLIER_HANDLING_COST_EUR,
            currency="EUR",
            source="operator_confirmed:proforma_handling_fees",
        ),
        "supplier_freight_quoted_eur": _money_field(
            SUPPLIER_FREIGHT_QUOTED_EUR,
            currency="EUR",
            source="operator_confirmed:proforma_freight_line",
        ),
        "supplier_amount_paid_eur": _money_field(
            SUPPLIER_AMOUNT_PAID_EUR,
            currency="EUR",
            source="operator_confirmed:wise_transfer",
        ),
        "wise_total_paid_usd": _money_field(
            WISE_TOTAL_PAID_USD,
            currency="USD",
            source="operator_confirmed:wise_card_settlement",
        ),
        "supplier_payment_transfer_id": {
            "value": SUPPLIER_PAYMENT_TRANSFER_ID,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed:wise_transfer_confirmation",
            "needs_review": False,
        },
        "supplier_payment_method": {
            "value": SUPPLIER_PAYMENT_METHOD,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
        "freight_status": {
            "value": FREIGHT_STATUS,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed:serva_awaiting_dhl_account",
            "needs_review": False,
        },
        "reconciliation_status": {
            "value": RECONCILIATION_STATUS,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed:363_minus_145_equals_218",
            "needs_review": False,
        },
        "deal_status": {
            "value": DEAL_STATUS,
            "confidence": "operator_confirmed",
            "source": "operator_confirmed",
            "needs_review": False,
        },
    }


def build_confirmed_events() -> list[dict[str, Any]]:
    return [
        {
            "event_type": "client_po_received",
            "event_at": "2026-05-14T12:00:00-04:00",
            "actor_email": "cgaray@ceaf.cl",
            "summary": "CEAF OC 26172 received",
            "confidence": "operator_confirmed",
        },
        {
            "event_type": "client_invoice_sent",
            "event_at": f"{INVOICE_SENT_TO_CLIENT_DATE}T12:00:00-04:00",
            "actor_email": "contacto@origenlab.cl",
            "summary": "OrigenLab Factura 6 and bank details sent to CEAF",
            "confidence": "operator_confirmed",
        },
        {
            "event_type": "supplier_po_sent",
            "event_at": f"{SUPPLIER_PROFORMA_DATE}T12:00:00+02:00",
            "counterparty_email": "order@serva.de",
            "summary": f"OrigenLab PO {SUPPLIER_PO_NUMBER} to SERVA",
            "confidence": "operator_confirmed",
        },
        {
            "event_type": "supplier_invoice_received",
            "event_at": f"{SUPPLIER_PROFORMA_DATE}T12:00:00+02:00",
            "counterparty_email": "order@serva.de",
            "summary": f"SERVA proforma {SUPPLIER_PROFORMA_NUMBER} total EUR 363.00",
            "confidence": "operator_confirmed",
        },
        {
            "event_type": "client_payment_received",
            "event_at": CLIENT_PAYMENT_AT,
            "actor_email": "fgonzalez@ceaf.cl",
            "subject": CLIENT_PAYMENT_SUBJECT,
            "amount_gross_clp": CLIENT_PAYMENT_RECEIVED_CLP,
            "amount_net_clp": CLIENT_SALE_AMOUNT_NET_CLP,
            "iva_amount_clp": CLIENT_IVA_AMOUNT_CLP,
            "iva_rate": float(CLIENT_IVA_RATE),
            "currency": "CLP",
            "operation_id": CLIENT_PAYMENT_OPERATION_ID,
            "summary": (
                "BancoChile transfer FACTURA 6 — CLP 1,499,400 gross "
                "(net CLP 1,260,000 + IVA CLP 239,400)"
            ),
            "confidence": "operator_confirmed",
        },
        {
            "event_type": "supplier_payment_sent",
            "event_at": WISE_FUNDED_AT,
            "counterparty_email": "order@serva.de",
            "amount": str(SUPPLIER_AMOUNT_PAID_EUR),
            "currency": "EUR",
            "transfer_id": SUPPLIER_PAYMENT_TRANSFER_ID,
            "wise_total_paid_usd": str(WISE_TOTAL_PAID_USD),
            "summary": f"Wise EUR {SUPPLIER_AMOUNT_PAID_EUR} to SERVA (transfer {SUPPLIER_PAYMENT_TRANSFER_ID})",
            "confidence": "operator_confirmed",
        },
        {
            "event_type": "logistics_pending",
            "event_at": WISE_FUNDS_AVAILABLE_DATE,
            "summary": (
                "SERVA funds available ~30 May 2026; shipment pending DHL account / external freight"
            ),
            "delivery_estimate": DELIVERY_ESTIMATE_WEEKS,
            "confidence": "operator_confirmed",
        },
    ]


def build_client_vat_breakdown() -> dict[str, Any]:
    """CEAF quotation line totals (operator-confirmed; matches Factura 6 / BancoChile)."""
    lines = [
        {"line": 1, "description": "BlueSlick 250 ml", "ref_code": "4250001", "net_clp": 695_000},
        {
            "line": 2,
            "description": "N,N,N',N'-Tetramethyl-ethylenediamine 25 ml",
            "ref_code": "3593002",
            "net_clp": 545_000,
        },
        {"line": 3, "description": "Envío", "ref_code": "E01", "net_clp": 20_000},
    ]
    subtotal = sum(row["net_clp"] for row in lines)
    return {
        "currency": "CLP",
        "iva_rate": float(CLIENT_IVA_RATE),
        "lines": lines,
        "subtotal_net_clp": subtotal,
        "iva_amount_clp": CLIENT_IVA_AMOUNT_CLP,
        "total_gross_clp": CLIENT_SALE_AMOUNT_GROSS_CLP,
        "payment_received_clp": CLIENT_PAYMENT_RECEIVED_CLP,
        "subtotal_matches_confirmed_net": subtotal == CLIENT_SALE_AMOUNT_NET_CLP,
    }
