"""Regression and characterization tests for warm-case sender/subject routing."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from origenlab_email_pipeline.warm_case_classification import infer_warm_case_category
from origenlab_email_pipeline.warm_case_role_classification import infer_warm_case_role_category
from origenlab_email_pipeline.warm_case_sender_rules import (
    CLIENT_OC_POST_SALE_MARKERS,
    CYBERDAY_CAMPAIGN_SUBJECT,
    INTERNAL_OPERATOR_DOMAINS,
    INTERNAL_OPERATOR_EMAILS,
    PAYMENT_ADMIN_TEXT_MARKERS,
    REAL_CLIENT_DOMAINS,
    SUPPLIER_VENDOR_DOMAINS,
    contact_email_from_recipients,
    contact_email_from_sender,
    email_domain,
    is_chile_institution_client_domain,
    is_internal_operator_contact,
    is_real_client_domain,
    is_supplier_vendor_domain,
    looks_like_auto_reply_text,
    looks_like_cesmec_catalogue_client_thread,
    looks_like_client_equipment_opportunity_thread,
    looks_like_client_oc_post_sale_subject,
    looks_like_cyberday_bulk_campaign_subject,
    looks_like_internal_admin_thread,
    looks_like_internal_forwarded_client_quote_request,
    looks_like_logistics_admin_contact,
    looks_like_payment_admin_thread,
    looks_like_real_supplier_quote_content,
    looks_like_security_notification,
    looks_like_supplier_followup_thread,
    looks_like_supplier_marketing_thread,
    looks_like_supplier_quote_response,
    looks_like_system_noise_contact,
    should_keep_visible_despite_suppression,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "origenlab_email_pipeline"
    / "warm_case_sender_rules.py"
)

# Symbols imported by warm_case_role_classification (caller contract).
_ROLE_CLASSIFICATION_IMPORTS = (
    "contact_email_from_recipients",
    "contact_email_from_sender",
    "email_domain",
    "is_internal_operator_contact",
    "is_real_client_domain",
    "is_supplier_vendor_domain",
    "looks_like_auto_reply_text",
    "looks_like_cesmec_catalogue_client_thread",
    "looks_like_client_equipment_opportunity_thread",
    "looks_like_client_oc_post_sale_subject",
    "looks_like_client_waiting_review_ack",
    "looks_like_contact_routing_notice",
    "looks_like_cyberday_bulk_campaign_subject",
    "looks_like_idiem_auto_acknowledgement",
    "looks_like_internal_admin_thread",
    "looks_like_internal_forwarded_client_quote_request",
    "looks_like_logistics_admin_contact",
    "looks_like_low_intent_client_acknowledgement",
    "looks_like_payment_admin_thread",
    "looks_like_supplier_followup_thread",
    "looks_like_supplier_quote_response",
    "looks_like_supplier_marketing_thread",
    "looks_like_system_noise_contact",
    "looks_like_unach_hielscher_supplier_wait",
    "should_keep_visible_despite_suppression",
)


def _row(sender: str, subject: str) -> dict:
    return {
        "email_id": 1,
        "sender_preview": sender,
        "subject_preview": subject,
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
    }


def test_google_security_alert_not_client_reply() -> None:
    sender = "Google <no-reply@accounts.google.com>"
    subject = "Alerta de seguridad"
    assert looks_like_security_notification(sender, subject, contact_email="no-reply@accounts.google.com")
    assert (
        infer_warm_case_category(_row(sender, subject), enrichment_available=False, include_noise=False)
        == "bounce"
    )


def test_eppendorf_registration_is_supplier() -> None:
    sender = "Eppendorf <eppendorf@eppendorf.com>"
    subject = "Please confirm your registration!"
    assert looks_like_supplier_marketing_thread(
        contact_email="eppendorf@eppendorf.com",
        sender=sender,
        subject=subject,
    )
    assert (
        infer_warm_case_category(_row(sender, subject), enrichment_available=False, include_noise=False)
        == "supplier_reply"
    )


def test_valuenindustrial_sales_is_supplier() -> None:
    assert (
        infer_warm_case_category(
            _row("sales@valuenindustrial.com", "Product line 2026"),
            enrichment_available=False,
            include_noise=False,
        )
        == "supplier_reply"
    )


def test_gzfanbolun_sales_is_supplier() -> None:
    assert (
        infer_warm_case_category(
            _row("sales001@gzfanbolun.com", "Lab equipment promo"),
            enrichment_available=False,
            include_noise=False,
        )
        == "supplier_reply"
    )


def test_yuanhuai_yhchem_is_supplier() -> None:
    assert (
        infer_warm_case_category(
            _row("jizhendong@yuanhuai.com", "YHCHEM catalog offer"),
            enrichment_available=False,
            include_noise=False,
        )
        == "supplier_reply"
    )


def test_ceaf_bank_details_payment_admin_thread() -> None:
    assert looks_like_payment_admin_thread(
        "lhidalgo@ceaf.cl",
        "Solicita datos Bancarios",
        snippet="factura N°06 y proceder al pago",
    )


def test_ceaf_oc_not_payment_admin() -> None:
    assert not looks_like_payment_admin_thread("cgaray@ceaf.cl", "Remite OC N º 26172")
    assert looks_like_client_oc_post_sale_subject("Remite OC N º 26172")


def test_banco_factura_payment_admin_domain() -> None:
    assert looks_like_payment_admin_thread(
        "serviciodetransferencias@bancochile.cl",
        "FACTURA 6",
    )


def test_gmail_cotizacion_stays_waiting_supplier_not_client() -> None:
    assert (
        infer_warm_case_category(
            _row(
                "aliro.ramirezf@gmail.com",
                "COTIZACION OSMOMETRO LOSER 16 M EN M.MOLL",
            ),
            enrichment_available=False,
            include_noise=False,
        )
        == "waiting_supplier"
    )


def test_portuguese_resposta_automatica_is_auto_reply() -> None:
    assert looks_like_auto_reply_text("RES: Resposta automática: Cotización")
    assert not looks_like_real_supplier_quote_content(
        "RES: Resposta automática: Cotización",
        "Esta é uma resposta automática.",
    )
    assert not looks_like_supplier_quote_response(
        "noreply@ika.net.br",
        "RES: Resposta automática: Cotización",
        snippet="Esta é uma resposta automática.",
    )


def test_beatriz_real_quote_passes_supplier_quote_gate() -> None:
    assert looks_like_supplier_quote_response(
        "beatriz.bonon@ika.net.br",
        "RE: IKA RV10.70 price response",
        snippet="Monto 112,00 stock disponible",
    )


def test_internal_forwarded_quote_request_detected_as_client_forward() -> None:
    assert looks_like_internal_forwarded_client_quote_request(
        contact_email="contacto@labdelivery.cl",
        subject="RV: Solicitud de Cotización Tubo Vapor IKA RV10.70 3812200// RG ENERGIA SPA",
        snippet="Solicitud cliente externa",
        sender="Tatiana Vivanco <contacto@labdelivery.cl>",
    )


# --- Characterization: public constants -------------------------------------------------


def test_public_domain_constants_non_empty() -> None:
    assert "origenlab.cl" in INTERNAL_OPERATOR_DOMAINS
    assert "contacto@origenlab.cl" in INTERNAL_OPERATOR_EMAILS
    assert "ceaf.cl" in REAL_CLIENT_DOMAINS
    assert "eppendorf.com" in SUPPLIER_VENDOR_DOMAINS
    assert "datos bancarios" in PAYMENT_ADMIN_TEXT_MARKERS
    assert "remite oc" in CLIENT_OC_POST_SALE_MARKERS


def test_cyberday_campaign_subject_spanish_origenlab_wording() -> None:
    assert "CYBERDAY" in CYBERDAY_CAMPAIGN_SUBJECT
    assert "equipos de laboratorio" in CYBERDAY_CAMPAIGN_SUBJECT
    assert "junio" in CYBERDAY_CAMPAIGN_SUBJECT


# --- Characterization: email parsing / boundaries ---------------------------------------


def test_contact_email_from_sender_empty_and_invalid() -> None:
    assert contact_email_from_sender(None) == ""
    assert contact_email_from_sender("") == ""
    assert contact_email_from_sender("not-an-email") == ""
    assert contact_email_from_sender("Vendor <sales@ika.net.br>") == "sales@ika.net.br"


def test_contact_email_from_recipients_skips_internal_operator() -> None:
    raw = "Tatiana <contacto@origenlab.cl>, Cliente <cliente@hospital.cl>"
    assert contact_email_from_recipients(raw) == "cliente@hospital.cl"


def test_email_domain_missing_at_sign() -> None:
    assert email_domain("") == ""
    assert email_domain("   ") == ""
    assert email_domain("nodomain") == ""
    assert email_domain("user@CEAF.CL") == "ceaf.cl"


def test_is_internal_operator_contact_by_email_and_domain() -> None:
    assert is_internal_operator_contact("contacto@origenlab.cl")
    assert is_internal_operator_contact("ops@labdelivery.cl")
    assert not is_internal_operator_contact("buyer@hospital.cl")


def test_is_chile_institution_client_domain_boundaries() -> None:
    assert is_chile_institution_client_domain("universidad.cl")
    assert not is_chile_institution_client_domain("gmail.com")
    assert not is_chile_institution_client_domain("eppendorf.com")
    assert not is_chile_institution_client_domain("origenlab.cl")


# --- Characterization: rule precedence (low-level helpers) ------------------------------


def test_internal_admin_precedence_forwarded_quote_exception() -> None:
    """Internal operator + SERVA markers → admin; forwarded RV cotización → not admin."""
    assert looks_like_internal_admin_thread(
        "contacto@origenlab.cl",
        "re: serva payment transfer",
        sender="contacto@origenlab.cl",
    )
    assert not looks_like_internal_admin_thread(
        "contacto@labdelivery.cl",
        "RV: Solicitud de Cotización Tubo Vapor IKA RV10.70",
        snippet="solicitud cliente externa",
        sender="Tatiana <contacto@labdelivery.cl>",
    )
    assert looks_like_internal_forwarded_client_quote_request(
        contact_email="contacto@labdelivery.cl",
        subject="RV: Solicitud de Cotización Tubo Vapor IKA RV10.70",
        snippet="rg energia",
        sender="contacto@labdelivery.cl",
    )


def test_supplier_quote_weak_subject_requires_price_content() -> None:
    assert not looks_like_supplier_quote_response(
        "beatriz.bonon@ika.net.br",
        "RE: follow up",
        snippet="thanks for your email",
    )
    assert looks_like_supplier_quote_response(
        "beatriz.bonon@ika.net.br",
        "RE: price list",
        snippet="USD 112.00 stock disponible",
    )


def test_supplier_followup_without_price_not_quote_response() -> None:
    assert looks_like_supplier_followup_thread(
        "sales@valuenindustrial.com",
        "RE: shipping address for quotation",
        snippet="please send address to calculate shipping",
    )
    assert not looks_like_real_supplier_quote_content(
        "RE: shipping address",
        "please send address to calculate shipping",
    )


def test_system_noise_includes_security_and_mailer_daemon() -> None:
    assert looks_like_system_noise_contact(
        "no-reply@accounts.google.com",
        "Google <no-reply@accounts.google.com>",
        "Alerta de seguridad",
    )
    assert looks_like_system_noise_contact(
        "",
        "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
        "Delivery Status Notification",
    )


def test_security_notification_spanish_and_english_markers() -> None:
    assert looks_like_security_notification(
        "Google <no-reply@accounts.google.com>",
        "Alerta de seguridad",
        contact_email="no-reply@accounts.google.com",
    )
    assert looks_like_security_notification(
        "Google <no-reply@accounts.google.com>",
        "Critical security alert",
        contact_email="no-reply@accounts.google.com",
    )
    assert not looks_like_security_notification(
        "buyer@hospital.cl",
        "Cotización equipos",
        contact_email="buyer@hospital.cl",
    )


def test_cyberday_subject_exact_and_normalized_dash_variants() -> None:
    assert looks_like_cyberday_bulk_campaign_subject(CYBERDAY_CAMPAIGN_SUBJECT)
    variant = CYBERDAY_CAMPAIGN_SUBJECT.replace("—", "–")
    assert looks_like_cyberday_bulk_campaign_subject(variant)
    assert not looks_like_cyberday_bulk_campaign_subject("CYBERDAY promo genérica")


def test_should_keep_visible_suppression_categories_and_cyberday_exception() -> None:
    assert should_keep_visible_despite_suppression(
        "sales@ika.net.br",
        "RE: price",
        category="supplier_reply",
    )
    assert not should_keep_visible_despite_suppression(
        "cliente@hospital.cl",
        CYBERDAY_CAMPAIGN_SUBJECT,
        category="waiting_client",
    )
    assert should_keep_visible_despite_suppression(
        "lhidalgo@ceaf.cl",
        "Remite OC N 26172",
        category="bounce",
    )
    assert should_keep_visible_despite_suppression(
        "serviciodetransferencias@bancochile.cl",
        "FACTURA 6",
        category="unknown_category",
    )


def test_logistics_admin_dhl_domain_and_spanish_cues() -> None:
    assert looks_like_logistics_admin_contact("ops@dhl.com", "Propuesta comercial DHL")
    assert looks_like_logistics_admin_contact(
        "cliente@hospital.cl",
        "Solicitud cuenta importación",
        snippet="cuenta importacion DHL",
    )


def test_cesmec_catalogue_client_spanish_markers() -> None:
    assert looks_like_cesmec_catalogue_client_thread(
        "contact@bureauveritas.com",
        "CESMEC catálogo metrología balances",
        snippet="bureau veritas",
    )


def test_client_equipment_opportunity_unach_hielscher_haystack() -> None:
    assert looks_like_client_equipment_opportunity_thread(
        "susanaalfaro@unach.cl",
        "RE: [RCH-123] Hielscher UIP2000 escalamiento universidad",
        snippet="extracción ultrason",
    )


# --- Characterization: role classifier precedence (caller integration) ----------------


def _role_row(
    *,
    sender: str,
    subject: str,
    source_file: str = "gmail:contacto@origenlab.cl/INBOX",
    snippet: str | None = None,
    recipients: str | None = None,
) -> dict:
    row: dict = {
        "email_id": 1,
        "sender_preview": sender,
        "subject_preview": subject,
        "source_file": source_file,
    }
    if snippet is not None:
        row["snippet"] = snippet
    if recipients is not None:
        row["recipients_preview"] = recipients
    return row


def test_role_precedence_cyberday_sent_folder_before_supplier_vendor() -> None:
    row = _role_row(
        sender="contacto@origenlab.cl",
        subject=CYBERDAY_CAMPAIGN_SUBJECT,
        source_file="gmail:contacto@origenlab.cl/[Gmail]/Enviados",
    )
    assert (
        infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
        == "campaign_outreach"
    )


def test_role_precedence_internal_forward_before_internal_admin() -> None:
    row = _role_row(
        sender="Tatiana <contacto@labdelivery.cl>",
        subject="RV: Solicitud de Cotización IKA RV10.70 3812200 RG ENERGIA",
        snippet="solicitud de cotizacion cliente externa",
    )
    assert (
        infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
        == "client_opportunity"
    )


def test_role_precedence_system_noise_before_payment_admin() -> None:
    row = _role_row(
        sender="Google <no-reply@accounts.google.com>",
        subject="Alerta de seguridad",
    )
    assert (
        infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
        == "system_noise"
    )


def test_role_precedence_payment_admin_on_ceaf_bank_details() -> None:
    row = _role_row(
        sender="lhidalgo@ceaf.cl",
        subject="Solicita datos Bancarios",
        snippet="factura N°06 y proceder al pago",
    )
    assert (
        infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
        == "payment_admin"
    )


# --- Characterization: module contract ------------------------------------------------


def test_warm_case_sender_rules_no_streamlit_imports() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "streamlit" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            assert "streamlit" not in (node.module or "").lower()


@pytest.mark.parametrize("name", _ROLE_CLASSIFICATION_IMPORTS)
def test_role_classification_caller_imports_remain_exported(name: str) -> None:
    import origenlab_email_pipeline.warm_case_sender_rules as mod

    assert hasattr(mod, name), f"missing export for role classifier: {name}"
    assert callable(getattr(mod, name))


def test_is_supplier_vendor_domain_matches_public_frozenset() -> None:
    assert is_supplier_vendor_domain("serva.de")
    assert is_real_client_domain("ceaf.cl")
    assert not is_supplier_vendor_domain("ceaf.cl")
