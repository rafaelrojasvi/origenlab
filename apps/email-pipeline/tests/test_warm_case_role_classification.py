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
