"""Regression tests for warm-case sender/subject routing."""

from __future__ import annotations

from origenlab_email_pipeline.warm_case_classification import infer_warm_case_category
from origenlab_email_pipeline.warm_case_sender_rules import (
    looks_like_client_oc_post_sale_subject,
    looks_like_payment_admin_thread,
    looks_like_security_notification,
    looks_like_supplier_marketing_thread,
    looks_like_internal_forwarded_client_quote_request,
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


def test_internal_forwarded_quote_request_detected_as_client_forward() -> None:
    assert looks_like_internal_forwarded_client_quote_request(
        contact_email="contacto@labdelivery.cl",
        subject="RV: Solicitud de Cotización Tubo Vapor IKA RV10.70 3812200// RG ENERGIA SPA",
        snippet="Solicitud cliente externa",
        sender="Tatiana Vivanco <contacto@labdelivery.cl>",
    )
