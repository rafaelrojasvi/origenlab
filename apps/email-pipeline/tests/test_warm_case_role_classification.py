"""Phase 7A regression tests for role-level warm-case classification."""

from __future__ import annotations

from origenlab_email_pipeline.warm_case_classification import infer_warm_case_role
from origenlab_email_pipeline.warm_case_role_classification import infer_warm_case_role_category


def _row(
    *,
    sender: str,
    subject: str,
    contact_email: str | None = None,
    snippet: str = "",
    has_positive_signal: bool = False,
) -> dict:
    return {
        "email_id": 1,
        "sender_preview": sender,
        "subject_preview": subject,
        "contact_email": contact_email,
        "snippet": snippet,
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
        "has_positive_signal": has_positive_signal,
    }


def test_sebastian_re_serva_is_internal_admin_not_client_response() -> None:
    row = _row(
        sender="Sebastian Rojas <sebastian.rojas.vivanco@gmail.com>",
        subject="Re: serva",
        contact_email="sebastian.rojas.vivanco@gmail.com",
        snippet="Wise transfer note for SERVA invoice",
    )
    role = infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
    assert role == "internal_admin"
    assert role not in ("client_response", "client_opportunity")


def test_beatriz_ika_quote_is_supplier_quote_received() -> None:
    row = _row(
        sender="Beatriz Bonon <beatriz.bonon@ika.net.br>",
        subject="RE: IKA RV10.70 price response",
        contact_email="beatriz.bonon@ika.net.br",
    )
    role = infer_warm_case_role(row, enrichment_available=False, include_noise=False)
    assert role == "supplier_quote_received"
    assert role != "client_opportunity"


def test_internal_forwarded_rg_energia_quote_is_client_opportunity() -> None:
    row = _row(
        sender="Tatiana Vivanco <contacto@labdelivery.cl>",
        subject="RV: Solicitud de Cotización Tubo Vapor IKA RV10.70 3812200// RG ENERGIA SPA",
        contact_email="contacto@labdelivery.cl",
        snippet="Reenvío de solicitud cliente RG ENERGIA SPA para tubo vapor",
    )
    role = infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
    assert role == "client_opportunity"


def test_ika_autoresponse_is_system_noise_not_supplier_quote() -> None:
    row = _row(
        sender="IKA Brasil <noreply@ika.net.br>",
        subject="RES: Resposta automática: Cotización",
        contact_email="noreply@ika.net.br",
        snippet="Esta é uma resposta automática. Retornaremos em breve.",
    )
    role = infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
    assert role == "system_noise"
    assert role != "supplier_quote_received"


def test_beatriz_ika_quote_with_price_stays_supplier_quote_received() -> None:
    row = _row(
        sender="Beatriz Bonon <beatriz.bonon@ika.net.br>",
        subject="RES: Solicitud de Cotización Tubo Vapor IKA RV10.70 3812200",
        contact_email="beatriz.bonon@ika.net.br",
        snippet="Monto 112,00 — stock disponible para 3 unidades RV10.70",
    )
    role = infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
    assert role == "supplier_quote_received"


def test_crtop_reactor_quote_is_supplier_quote_received() -> None:
    row = _row(
        sender="Ariel <ariel@crtopmachine.com>",
        subject="Re: Thank you very much for your inquiry about our reactor.",
        contact_email="ariel@crtopmachine.com",
        snippet="CRTOP quotation Lab Reactor OLT-HP-5L, EXW USD 10600",
    )
    role = infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
    assert role == "supplier_quote_received"


def test_dhl_account_email_is_logistics_admin() -> None:
    row = _row(
        sender="Monica Silva <monica.silva@dhl.com>",
        subject="PROPUESTA COMERCIAL DHL",
        contact_email="monica.silva@dhl.com",
    )
    assert infer_warm_case_role_category(row, enrichment_available=False, include_noise=False) == (
        "logistics_admin"
    )


def test_bancochile_factura_is_payment_admin() -> None:
    row = _row(
        sender="Banco Chile <serviciodetransferencias@bancochile.cl>",
        subject="FACTURA 6",
        contact_email="serviciodetransferencias@bancochile.cl",
    )
    assert infer_warm_case_role_category(row, enrichment_available=False, include_noise=False) == (
        "payment_admin"
    )


def test_google_security_alert_is_system_noise() -> None:
    row = _row(
        sender="Google <no-reply@accounts.google.com>",
        subject="Alerta de seguridad",
        contact_email="no-reply@accounts.google.com",
    )
    role = infer_warm_case_role_category(row, enrichment_available=False, include_noise=False)
    assert role == "system_noise"
    assert role not in ("client_response", "client_opportunity")


def test_udec_sonicador_reply_is_client_opportunity() -> None:
    row = _row(
        sender="Contacto UdeC <contacto@udec.cl>",
        subject="Re: cotización sonicador ultrasonidos",
        contact_email="contacto@udec.cl",
        has_positive_signal=True,
    )
    role = infer_warm_case_role_category(row, enrichment_available=True, include_noise=False)
    assert role in ("client_opportunity", "client_response")
    assert "supplier" not in role
