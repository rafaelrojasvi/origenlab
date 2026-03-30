from __future__ import annotations

from origenlab_email_pipeline.commercial_intel_rules import derive_email_signal_facts


def test_rules_emit_positive_quote_and_procurement_signals() -> None:
    facts = derive_email_signal_facts(
        subject="Solicitud de cotizacion y orden de compra",
        sender_raw="Compras U. Demo <compras@udemo.cl>",
        recipients_raw="contacto@origenlab.cl",
        top_reply_clean="Necesitamos cotizacion formal y condiciones para OC.",
        full_body_clean="",
        sender_domain="udemo.cl",
        internal_domains={"origenlab.cl"},
        vendor_domains=set(),
        existing_client_domains=set(),
    )
    codes = {f.signal_code for f in facts}
    assert "quote_intent" in codes
    assert "procurement_intent" in codes


def test_rules_emit_vendor_and_invoice_suppressions() -> None:
    facts = derive_email_signal_facts(
        subject="Factura pendiente y despacho proveedor",
        sender_raw="Proveedor Demo <ventas@supplier.cl>",
        recipients_raw="contacto@origenlab.cl",
        top_reply_clean="Adjuntamos factura y guia de despacho.",
        full_body_clean="",
        sender_domain="supplier.cl",
        internal_domains={"origenlab.cl"},
        vendor_domains={"supplier.cl"},
        existing_client_domains=set(),
    )
    suppression_codes = {f.signal_code for f in facts if f.signal_kind == "suppression"}
    assert "vendor_suppression" in suppression_codes
    assert "invoice_payment_suppression" in suppression_codes
    assert "logistics_suppression" in suppression_codes

