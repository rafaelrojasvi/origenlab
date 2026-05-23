"""Response-time warm-case normalization (read-only; no SQLite writes)."""

from __future__ import annotations

import re

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

_AUTO_REPLY_SUBJECT_MARKERS: tuple[str, ...] = (
    "automatic reply",
    "auto-reply",
    "out of office",
    "fuera de oficina",
    "respuesta automática",
    "respuesta automatica",
)

_LOGISTICS_VENDOR_DOMAINS: frozenset[str] = frozenset({"dhl.com"})

_SUPPLIER_VENDOR_DOMAINS: frozenset[str] = frozenset(
    {
        "dlabsci.com",
        "crtopmachine.com",
        "asynt.com",
        "ollital.com",
        "serva.de",
        "ortoalresa.com",
    }
)

_PAYMENT_SENDER_DOMAINS: frozenset[str] = frozenset({"bancochile.cl"})

_PAYMENT_SUBJECT_KEYWORDS: tuple[str, ...] = (
    "factura",
    "comprobante de transferencia",
    "transferencia",
    "pago",
)

_NEXT_ACTION_BY_CATEGORY: dict[str, str] = {
    "auto_reply": "Ignorar respuesta automática; no requiere acción comercial.",
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

_PRESERVE_CATEGORIES: frozenset[str] = frozenset({"quote_sent", "waiting_client", "waiting_supplier"})


def _email_domain(contact_email: str) -> str:
    email = (contact_email or "").strip().lower()
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1]


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


def _infer_status(category: WarmCaseCategory, prior: WarmCaseStatus) -> WarmCaseStatus:
    if category == "auto_reply":
        return "problem"
    if category == "payment_admin":
        return "open"
    if category == "vendor_logistics":
        return "open"
    if category == "quote_sent":
        return "quoted"
    if category in ("waiting_supplier", "waiting_client"):
        return "waiting"
    if category == "bounce":
        return "problem"
    if category == "supplier_reply" and prior in ("waiting", "quoted"):
        return prior
    return prior if prior in ("open", "waiting", "quoted", "problem") else "new"


def resolve_normalized_category(item: WarmCaseItem) -> WarmCaseCategory:
    """Deterministic category override from contact domain and subject."""
    if item.category in _PRESERVE_CATEGORIES:
        return item.category  # type: ignore[return-value]

    if is_auto_reply_subject(item.subject):
        return "auto_reply"

    domain = _email_domain(item.contact_email)
    subject_l = (item.subject or "").lower()

    if domain in _PAYMENT_SENDER_DOMAINS or _subject_has_payment_signal(item.subject):
        return "payment_admin"

    if domain in _LOGISTICS_VENDOR_DOMAINS or "dhl" in subject_l:
        return "vendor_logistics"

    if domain in _SUPPLIER_VENDOR_DOMAINS:
        return "supplier_reply"

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


def normalize_warm_case_items(
    items: list[WarmCaseItem],
    *,
    include_noise: bool = False,
    category_filter: str | None = None,
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
    return out
