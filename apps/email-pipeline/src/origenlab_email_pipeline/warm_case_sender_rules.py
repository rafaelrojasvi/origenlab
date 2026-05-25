"""Shared warm-case sender/subject heuristics (read-only; API + SQLite promotion)."""

from __future__ import annotations

from origenlab_email_pipeline.business_mart import emails_in

INTERNAL_OPERATOR_DOMAINS: frozenset[str] = frozenset({"origenlab.cl", "labdelivery.cl"})

_PAYMENT_ADMIN_DOMAINS: frozenset[str] = frozenset({"bancochile.cl"})

_LOGISTICS_VENDOR_DOMAINS: frozenset[str] = frozenset({"dhl.com"})

# Existing-client / post-sale threads (not suppliers).
REAL_CLIENT_DOMAINS: frozenset[str] = frozenset({"ceaf.cl"})

# Domains that should never appear as «Clientes reales» (vendor / industrial suppliers).
SUPPLIER_VENDOR_DOMAINS: frozenset[str] = frozenset(
    {
        "asynt.com",
        "crtopmachine.com",
        "dlabsci.com",
        "eppendorf.com",
        "gzfanbolun.com",
        "ollital.com",
        "ortoalresa.com",
        "serva.de",
        "valuenindustrial.com",
        "yuanhuai.com",
    }
)

_SECURITY_CONTACT_DOMAINS: frozenset[str] = frozenset({"accounts.google.com"})

_SECURITY_SUBJECT_MARKERS: tuple[str, ...] = (
    "alerta de seguridad",
    "security alert",
    "critical security",
    "suspicious sign-in",
    "suspicious sign in",
    "new sign-in",
    "nuevo inicio de sesión",
    "nuevo inicio de sesion",
)

_ADMIN_SIGNUP_SUBJECT_MARKERS: tuple[str, ...] = (
    "confirm your registration",
    "please confirm your registration",
    "confirm your email",
    "verify your email",
    "email verification",
    "activate your account",
    "activar su cuenta",
)

_SUPPLIER_SUBJECT_MARKERS: tuple[str, ...] = (
    "supplier",
    "proveedor",
    "distrib",
    "hielscher",
    "ortoalresa",
    "serva.de",
    "ollital",
    "kern",
    "sartorius",
    "eppendorf",
    "yh chem",
    "yhchem",
    "fanbolun",
    "valuen",
)


def contact_email_from_sender(sender_preview: str | None) -> str:
    found = emails_in(sender_preview or "")
    return found[0].lower() if found else ""


def is_internal_operator_contact(contact_email: str) -> bool:
    email = (contact_email or "").strip().lower()
    if email == "contacto@origenlab.cl":
        return True
    return email_domain(email) in INTERNAL_OPERATOR_DOMAINS


def is_real_client_domain(domain: str) -> bool:
    return (domain or "").strip().lower() in REAL_CLIENT_DOMAINS


PAYMENT_ADMIN_TEXT_MARKERS: tuple[str, ...] = (
    "datos bancarios",
    "solicita datos banc",
    "cuenta corriente",
    "beneficiario",
    "factura n°",
    "factura nº",
    "factura n ",
    "factura no",
    "factura nro",
    "proceder al pago",
    "comprobante de transferencia",
    "transferencia",
    "registrarla en nuestro sistema",
    "registrar en nuestro sistema",
    "factura",
    "pago",
)

CLIENT_OC_POST_SALE_MARKERS: tuple[str, ...] = (
    "remite oc",
    "orden de compra",
    "re: remite oc",
)


def payment_admin_text_haystack(
    *,
    subject: str | None,
    snippet: str | None = None,
    account_name: str | None = None,
) -> str:
    return " ".join(
        [
            subject or "",
            snippet or "",
            account_name or "",
        ]
    ).lower()


def looks_like_payment_admin_thread(
    contact_email: str,
    subject: str | None,
    *,
    snippet: str | None = None,
    account_name: str | None = None,
) -> bool:
    if email_domain(contact_email) in _PAYMENT_ADMIN_DOMAINS:
        return True
    hay = payment_admin_text_haystack(
        subject=subject,
        snippet=snippet,
        account_name=account_name,
    )
    return any(marker in hay for marker in PAYMENT_ADMIN_TEXT_MARKERS)


def looks_like_payment_admin_contact(
    contact_email: str,
    subject: str | None,
    *,
    snippet: str | None = None,
    account_name: str | None = None,
) -> bool:
    return looks_like_payment_admin_thread(
        contact_email,
        subject,
        snippet=snippet,
        account_name=account_name,
    )


def looks_like_vendor_logistics_contact(contact_email: str, subject: str | None) -> bool:
    domain = email_domain(contact_email)
    sub = (subject or "").lower()
    if domain in _LOGISTICS_VENDOR_DOMAINS:
        return True
    return any(
        token in sub
        for token in (
            "dhl",
            "cuenta importación",
            "cuenta importacion",
            "propuesta comercial dhl",
            "solicitud cuenta",
        )
    )


def should_keep_visible_despite_suppression(
    contact_email: str,
    subject: str | None,
    *,
    category: str,
    snippet: str | None = None,
) -> bool:
    """Payment/logistics/supplier rows must stay in api.v_warm_case (status <> problem-only gate)."""
    if category in ("supplier_reply", "quote_sent", "waiting_supplier", "waiting_client"):
        return True
    if looks_like_payment_admin_contact(contact_email, subject, snippet=snippet):
        return True
    if looks_like_vendor_logistics_contact(contact_email, subject):
        return True
    if is_real_client_domain(email_domain(contact_email)) and looks_like_client_oc_post_sale_subject(
        subject,
        snippet=snippet,
    ):
        return True
    return False


def looks_like_client_oc_post_sale_subject(
    subject: str | None,
    *,
    snippet: str | None = None,
    account_name: str | None = None,
) -> bool:
    """CEAF/client OC threads — not bank-registration / payment setup."""
    hay = payment_admin_text_haystack(
        subject=subject,
        snippet=snippet,
        account_name=account_name,
    )
    if any(marker in hay for marker in CLIENT_OC_POST_SALE_MARKERS):
        return True
    return False


def looks_like_client_post_sale_subject(subject: str | None) -> bool:
    return looks_like_client_oc_post_sale_subject(subject)


def email_domain(contact_email: str) -> str:
    email = (contact_email or "").strip().lower()
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1]


def looks_like_security_notification(
    sender: str | None,
    subject: str | None,
    *,
    contact_email: str = "",
) -> bool:
    """Google / account security alerts — not commercial client threads."""
    email = (contact_email or "").strip().lower() or contact_email_from_sender(sender)
    domain = email_domain(email)
    sub = (subject or "").lower()
    snd = (sender or "").lower()

    if domain in _SECURITY_CONTACT_DOMAINS:
        if any(m in sub for m in _SECURITY_SUBJECT_MARKERS):
            return True
        if "seguridad" in sub or "security" in sub:
            return True

    if "accounts.google.com" in snd and ("seguridad" in sub or "security" in sub):
        return True
    return False


def is_supplier_vendor_domain(domain: str) -> bool:
    return (domain or "").strip().lower() in SUPPLIER_VENDOR_DOMAINS


def looks_like_supplier_admin_signup_subject(subject: str | None) -> bool:
    sub = (subject or "").lower()
    return any(m in sub for m in _ADMIN_SIGNUP_SUBJECT_MARKERS)


def looks_like_supplier_marketing_thread(
    *,
    contact_email: str,
    sender: str | None = None,
    subject: str | None = None,
) -> bool:
    """Vendor/supplier outreach that must not be labeled client_reply."""
    email = (contact_email or "").strip().lower() or contact_email_from_sender(sender)
    domain = email_domain(email)
    if is_supplier_vendor_domain(domain):
        return True

    sub = (subject or "").lower()
    snd = (sender or "").lower()
    if any(m in sub or m in snd for m in _SUPPLIER_SUBJECT_MARKERS):
        return True

    if looks_like_supplier_admin_signup_subject(subject):
        return True

    if email.startswith("sales@") or email.startswith("sales0"):
        if domain and domain not in {"gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "yahoo.com"}:
            return True

    return False
