"""Response-time warm-case normalization (read-only; no SQLite writes)."""

from __future__ import annotations

from origenlab_email_pipeline.warm_case_sender_rules import (
    REAL_CLIENT_DOMAINS,
    SUPPLIER_VENDOR_DOMAINS,
    email_domain,
    is_internal_operator_contact,
    is_real_client_domain,
    looks_like_client_post_sale_subject,
    looks_like_security_notification,
    looks_like_supplier_admin_signup_subject,
    looks_like_supplier_marketing_thread,
)

from origenlab_api.schemas.cases import WarmCaseCategory, WarmCaseItem, WarmCaseStatus

# Extended operator-facing categories (API output only).
NORMALIZED_WARM_CATEGORIES: frozenset[str] = frozenset(
    {
        "client_reply",
        "supplier_reply",
        "quote_sent",
        "waiting_supplier",
        "waiting_client",
        "bounce",
        "opportunity",
        "auto_reply",
        "vendor_logistics",
        "payment_admin",
    }
)

# Applied after normalization when positive_signal_only=True (Postgres/SQLite repos).
POST_NORMALIZE_POSITIVE_CATEGORIES: frozenset[str] = frozenset(
    {
        "client_reply",
        "supplier_reply",
        "quote_sent",
        "waiting_supplier",
        "waiting_client",
        "opportunity",
        "payment_admin",
        "vendor_logistics",
    }
)

_AUTO_REPLY_SUBJECT_MARKERS: tuple[str, ...] = (
    "automatic reply",
    "auto-reply",
    "out of office",
    "fuera de oficina",
    "respuesta automática",
    "respuesta automatica",
)

_LOGISTICS_VENDOR_DOMAINS: frozenset[str] = frozenset({"dhl.com"})

_PAYMENT_SENDER_DOMAINS: frozenset[str] = frozenset({"bancochile.cl"})

_PAYMENT_SUBJECT_KEYWORDS: tuple[str, ...] = (
    "factura",
    "comprobante de transferencia",
    "transferencia",
    "pago",
)

_LOGISTICS_SUBJECT_MARKERS: tuple[str, ...] = (
    "dhl",
    "cuenta importación",
    "cuenta importacion",
    "propuesta comercial dhl",
    "solicitud cuenta",
)

_NEXT_ACTION_BY_CATEGORY: dict[str, str] = {
    "auto_reply": "Ignorar alerta automática / registro; no requiere acción comercial.",
    "vendor_logistics": (
        "Revisar gestión logística/cuenta de importación; no cotizar al remitente."
    ),
    "supplier_reply": (
        "Leer propuesta del proveedor y vincularla al cliente/oportunidad correspondiente."
    ),
    "payment_admin": "Registrar/confirmar pago y asociarlo a factura/cliente; no cotizar.",
    "bounce": "Revisar NDR; no reenviar a la misma dirección sin corregir.",
    "quote_sent": "Confirmar si el cliente respondió; no duplicar cotización.",
    "waiting_client": "Esperar respuesta o seguimiento suave si pasó el plazo.",
    "waiting_supplier": "Seguimiento a proveedor por cotización pendiente.",
    "client_reply": "Responder hilo comercial; verificar specs antes de cotizar.",
    "opportunity": "Priorizar según señal comercial; validar equipo y plazo.",
}


def is_auto_reply_subject(subject: str | None) -> bool:
    sub = (subject or "").strip().lower()
    if not sub:
        return False
    if sub.startswith("automatic reply"):
        return True
    return any(marker in sub for marker in _AUTO_REPLY_SUBJECT_MARKERS)


def _subject_has_payment_signal(subject: str | None) -> bool:
    sub = (subject or "").lower()
    return any(kw in sub for kw in _PAYMENT_SUBJECT_KEYWORDS)


def _subject_has_logistics_signal(subject: str | None) -> bool:
    sub = (subject or "").lower()
    return any(kw in sub for kw in _LOGISTICS_SUBJECT_MARKERS)


def _infer_status(category: WarmCaseCategory, prior: WarmCaseStatus) -> WarmCaseStatus:
    if category in ("auto_reply", "bounce"):
        return "problem"
    if category == "payment_admin":
        return "open"
    if category == "vendor_logistics":
        return "open"
    if category == "quote_sent":
        return "quoted"
    if category in ("waiting_supplier", "waiting_client"):
        return "waiting"
    if category == "supplier_reply" and prior in ("waiting", "quoted"):
        return prior
    return prior if prior in ("open", "waiting", "quoted", "problem") else "new"


def resolve_normalized_category(item: WarmCaseItem) -> WarmCaseCategory:
    """Deterministic category override from contact domain and subject."""
    if is_internal_operator_contact(item.contact_email):
        return "auto_reply"

    if looks_like_security_notification(None, item.subject, contact_email=item.contact_email):
        return "auto_reply"

    if is_auto_reply_subject(item.subject):
        return "auto_reply"

    domain = email_domain(item.contact_email)
    subject_l = (item.subject or "").lower()

    if looks_like_supplier_marketing_thread(
        contact_email=item.contact_email,
        subject=item.subject,
    ) or looks_like_supplier_admin_signup_subject(item.subject):
        return "supplier_reply"

    if domain in _PAYMENT_SENDER_DOMAINS or _subject_has_payment_signal(item.subject):
        return "payment_admin"

    if domain in _LOGISTICS_VENDOR_DOMAINS or _subject_has_logistics_signal(item.subject):
        return "vendor_logistics"

    if domain in SUPPLIER_VENDOR_DOMAINS:
        return "supplier_reply"

    if is_real_client_domain(domain) and looks_like_client_post_sale_subject(item.subject):
        return "client_reply"

    if item.category in ("quote_sent", "waiting_client", "waiting_supplier"):
        return item.category  # type: ignore[return-value]

    if item.category == "client_reply":
        return "client_reply"

    return item.category  # type: ignore[return-value]


def normalize_warm_case_item(
    item: WarmCaseItem,
    *,
    include_noise: bool = False,
) -> WarmCaseItem | None:
    """
    Adjust category/status/next_action at response time.

    Returns None when the row should be omitted (auto-reply with noise excluded).
    """
    category = resolve_normalized_category(item)

    if category == "auto_reply" and not include_noise:
        return None

    status = _infer_status(category, item.status)
    next_action = _NEXT_ACTION_BY_CATEGORY.get(category, item.next_action)

    return item.model_copy(
        update={
            "category": category,
            "status": status,
            "next_action": next_action,
        }
    )


def filter_positive_normalized_items(items: list[WarmCaseItem]) -> list[WarmCaseItem]:
    """Keep operator-meaningful categories after response-time normalization."""
    return [item for item in items if item.category in POST_NORMALIZE_POSITIVE_CATEGORIES]


def normalize_warm_case_items(
    items: list[WarmCaseItem],
    *,
    include_noise: bool = False,
    category_filter: str | None = None,
    positive_signal_only: bool = False,
) -> list[WarmCaseItem]:
    """Normalize and optionally filter by post-normalization category."""
    needle = (category_filter or "").strip().lower()
    out: list[WarmCaseItem] = []
    for item in items:
        normalized = normalize_warm_case_item(item, include_noise=include_noise)
        if normalized is None:
            continue
        if needle and normalized.category != needle:
            continue
        out.append(normalized)
    if positive_signal_only:
        out = filter_positive_normalized_items(out)
    return out
