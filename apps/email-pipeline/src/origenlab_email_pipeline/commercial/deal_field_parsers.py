"""Regex helpers for commercial deal field extraction (read-only; no DB I/O)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Confidence = Literal["high", "medium", "low", "needs_review"]


@dataclass(frozen=True)
class FieldExtraction:
    value: str | Decimal | int | None
    confidence: Confidence
    source: str
    needs_review: bool = False


_SERVA_CUSTOMER_CODE = re.compile(r"\b310471\b")
_SUPPLIER_PO = re.compile(
    r"(?:PO|P\.O\.|purchase\s+order)\s*N[°ºo.]?\s*174[\s\-/]*26",
    re.IGNORECASE,
)
_SUPPLIER_PO_SHORT = re.compile(r"\b174[\s\-/]*26\b")
_CEAF_OC = re.compile(
    r"(?:OC|orden\s+de\s+compra)\s*N\s*[°ºo.]?\s*0*26172\b",
    re.IGNORECASE,
)
_CEAF_OC_SHORT = re.compile(r"\b26172\b")
_CLIENT_INVOICE = re.compile(
    r"Factura\s*(?:N[°ºo.]?\s*)?0*6\b",
    re.IGNORECASE,
)
_SUPPLIER_PROFORMA = re.compile(r"\bA2602545\b", re.IGNORECASE)
_EUR_218 = re.compile(
    r"(?:EUR|€)\s*218[,.]00|218[,.]00\s*(?:EUR|€)|\b218[,.]00\s*eur\b",
    re.IGNORECASE,
)
_CLP_SALE_GROSS = re.compile(
    r"(?:total|monto|importe|bruto|gross)[^\d]{0,40}([\d.]{5,12})\s*(?:clp|pesos)?",
    re.IGNORECASE,
)


def _first_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    if not text:
        return None
    return pattern.search(text)


def parse_serva_customer_code(text: str) -> FieldExtraction | None:
    m = _first_match(_SERVA_CUSTOMER_CODE, text)
    if not m:
        return None
    return FieldExtraction(value="310471", confidence="high", source="regex:310471")


def parse_supplier_po_number(text: str) -> FieldExtraction | None:
    m = _first_match(_SUPPLIER_PO, text) or _first_match(_SUPPLIER_PO_SHORT, text)
    if not m:
        return None
    conf: Confidence = "high" if "174" in m.group(0) and "26" in m.group(0) else "medium"
    return FieldExtraction(value="174-26", confidence=conf, source=f"regex:{m.group(0)[:40]}")


def parse_ceaf_oc_number(text: str) -> FieldExtraction | None:
    m = _first_match(_CEAF_OC, text)
    if m:
        return FieldExtraction(value="26172", confidence="high", source=f"regex:{m.group(0)[:40]}")
    if "ceaf" in text.lower() and _first_match(_CEAF_OC_SHORT, text):
        return FieldExtraction(value="26172", confidence="medium", source="regex:26172+ceaf_context")
    return None


def parse_client_invoice_number(text: str) -> FieldExtraction | None:
    m = _first_match(_CLIENT_INVOICE, text)
    if not m:
        return None
    return FieldExtraction(value="6", confidence="high", source=f"regex:{m.group(0)[:40]}")


def parse_supplier_proforma_number(text: str) -> FieldExtraction | None:
    m = _first_match(_SUPPLIER_PROFORMA, text)
    if not m:
        return None
    return FieldExtraction(value="A2602545", confidence="high", source="regex:A2602545")


def parse_supplier_payment_eur(text: str) -> FieldExtraction | None:
    m = _first_match(_EUR_218, text)
    if not m:
        return None
    return FieldExtraction(
        value=Decimal("218.00"),
        confidence="medium",
        source=f"regex:{m.group(0)[:40]}",
    )


def parse_client_sale_amount_clp(text: str) -> FieldExtraction:
    """Never invent a sale amount; return needs_review when not found."""
    m = _first_match(_CLP_SALE_GROSS, text)
    if not m:
        return FieldExtraction(
            value=None,
            confidence="needs_review",
            source="not_found",
            needs_review=True,
        )
    raw = m.group(1).replace(".", "")
    try:
        amount = int(raw)
    except ValueError:
        return FieldExtraction(
            value=None,
            confidence="needs_review",
            source="parse_error",
            needs_review=True,
        )
    return FieldExtraction(
        value=amount,
        confidence="low",
        source=f"regex:{m.group(0)[:60]}",
        needs_review=True,
    )


def chilean_iva_gross_from_net(net_clp: int, iva_rate: Decimal = Decimal("0.19")) -> int:
    """Round CLP gross = net * (1 + IVA rate), half-up to integer pesos."""
    gross = (Decimal(net_clp) * (Decimal("1") + iva_rate)).quantize(Decimal("1"))
    return int(gross)


def reconcile_supplier_payment_excluding_freight(
    *,
    invoice_total_eur: Decimal,
    freight_quoted_eur: Decimal,
    amount_paid_eur: Decimal,
) -> dict[str, object]:
    """Classify SERVA proforma vs Wise payment (freight excluded from wire)."""
    expected = invoice_total_eur - freight_quoted_eur
    product_plus_handling = invoice_total_eur - freight_quoted_eur
    reconciled = amount_paid_eur == expected
    return {
        "reconciliation_status": (
            "reconciled_excluding_supplier_freight" if reconciled else "needs_review"
        ),
        "supplier_invoice_total_eur": format(invoice_total_eur, "f"),
        "supplier_freight_quoted_eur": format(freight_quoted_eur, "f"),
        "supplier_amount_paid_eur": format(amount_paid_eur, "f"),
        "expected_payment_excluding_freight_eur": format(expected, "f"),
        "product_plus_handling_eur": format(product_plus_handling, "f"),
        "freight_excluded_from_wire": reconciled,
        "note": (
            "SERVA proforma total minus quoted freight equals Wise payment; "
            "freight via DHL account / external carrier."
            if reconciled
            else "Paid amount does not match proforma total minus freight."
        ),
    }


def extraction_to_json(field: FieldExtraction | None) -> dict[str, object] | None:
    if field is None:
        return None
    val = field.value
    if isinstance(val, Decimal):
        val = format(val, "f")
    return {
        "value": val,
        "confidence": field.confidence,
        "source": field.source,
        "needs_review": field.needs_review,
    }
