"""Shared warm-case sender/subject heuristics (read-only; API + SQLite promotion)."""

from __future__ import annotations

from origenlab_email_pipeline.business_mart import emails_in

INTERNAL_OPERATOR_DOMAINS: frozenset[str] = frozenset({"origenlab.cl", "labdelivery.cl"})

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


def looks_like_client_post_sale_subject(subject: str | None) -> bool:
    sub = (subject or "").lower()
    return any(
        token in sub
        for token in (
            "remite oc",
            "orden de compra",
            "datos bancarios",
            "solicita datos banc",
            "factura",
            "transferencia",
        )
    )


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
