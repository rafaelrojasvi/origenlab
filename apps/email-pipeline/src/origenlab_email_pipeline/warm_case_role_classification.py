"""Role-level warm-case triage categories (read-only; shared by API + promotion)."""

from __future__ import annotations

import re
from typing import Any, Literal

from origenlab_email_pipeline.cases_review_queue import looks_like_obvious_noise
from origenlab_email_pipeline.warm_case_sender_rules import (
    contact_email_from_sender,
    email_domain,
    is_internal_operator_contact,
    is_real_client_domain,
    is_supplier_vendor_domain,
    looks_like_auto_reply_subject,
    looks_like_client_oc_post_sale_subject,
    looks_like_internal_admin_thread,
    looks_like_logistics_admin_contact,
    looks_like_payment_admin_thread,
    looks_like_supplier_quote_response,
    looks_like_supplier_marketing_thread,
    looks_like_system_noise_contact,
    should_keep_visible_despite_suppression,
)

WarmCaseRoleCategory = Literal[
    "client_opportunity",
    "client_response",
    "supplier_quote_received",
    "supplier_followup",
    "payment_admin",
    "logistics_admin",
    "internal_admin",
    "system_noise",
    "bounce_problem",
    "deal_evidence_candidate",
    "quote_sent",
    "waiting_supplier",
    "waiting_client",
]

# Legacy storage categories (Postgres CHECK / promotion).
WarmCaseLegacyCategory = Literal[
    "client_reply",
    "supplier_reply",
    "quote_sent",
    "waiting_supplier",
    "waiting_client",
    "bounce",
    "opportunity",
]

_EQUIPMENT_KEYWORDS = (
    "centrifug",
    "ultrason",
    "sonicador",
    "reactor",
    "balanza",
    "incubad",
    "licitacion",
    "licitación",
    "equipo",
    "turrax",
)

_DEAL_EVIDENCE_MARKERS = (
    "serva",
    "ceaf",
    "orden de compra",
    "remite oc",
    "oc n",
    "po-",
    "deal_key",
)


def _bool_signal(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def _is_sent_folder(source_file: str | None) -> bool:
    s = (source_file or "").lower()
    return "enviados" in s or "sent mail" in s or "/sent" in s


def _row_contact_email(row: dict[str, Any]) -> str:
    explicit = row.get("contact_email")
    if isinstance(explicit, str) and "@" in explicit:
        return explicit.strip().lower()
    sender = row.get("sender_preview")
    return contact_email_from_sender(sender if isinstance(sender, str) else None)


def _row_subject(row: dict[str, Any]) -> str | None:
    subject = row.get("subject_preview") or row.get("subject")
    return subject if isinstance(subject, str) else None


def _row_sender(row: dict[str, Any]) -> str | None:
    sender = row.get("sender_preview")
    return sender if isinstance(sender, str) else None


def looks_like_deal_evidence_thread(
    contact_email: str,
    subject: str | None,
    *,
    snippet: str | None = None,
) -> bool:
    """CEAF/SERVA commercial-deal threads (link to deal timeline in Phase 7B)."""
    domain = email_domain(contact_email)
    hay = " ".join([subject or "", snippet or ""]).lower()
    if is_real_client_domain(domain) and looks_like_client_oc_post_sale_subject(
        subject,
        snippet=snippet,
    ):
        return True
    if any(marker in hay for marker in _DEAL_EVIDENCE_MARKERS):
        if "serva" in hay or is_real_client_domain(domain):
            return True
    return False


def infer_warm_case_role_category(
    row: dict[str, Any],
    *,
    enrichment_available: bool,
    include_noise: bool,
) -> WarmCaseRoleCategory:
    sender_s = _row_sender(row)
    subject_s = _row_subject(row)
    contact_email = _row_contact_email(row)
    snippet = row.get("snippet") if isinstance(row.get("snippet"), str) else None
    account_name = row.get("account_name") if isinstance(row.get("account_name"), str) else None

    if looks_like_obvious_noise(sender_s, subject_s):
        return "bounce_problem"

    if looks_like_auto_reply_subject(subject_s):
        return "system_noise"

    if looks_like_system_noise_contact(contact_email, sender_s, subject_s):
        return "system_noise"

    if looks_like_internal_admin_thread(
        contact_email,
        subject_s,
        snippet=snippet,
        sender=sender_s,
    ):
        return "internal_admin"

    if looks_like_payment_admin_thread(
        contact_email,
        subject_s,
        snippet=snippet,
        account_name=account_name,
    ):
        return "payment_admin"

    if looks_like_logistics_admin_contact(contact_email, subject_s, snippet=snippet):
        return "logistics_admin"

    if looks_like_deal_evidence_thread(contact_email, subject_s, snippet=snippet):
        return "deal_evidence_candidate"

    if looks_like_supplier_quote_response(
        contact_email,
        subject_s,
        snippet=snippet,
        sender=sender_s,
    ):
        return "supplier_quote_received"

    if looks_like_supplier_marketing_thread(
        contact_email=contact_email,
        sender=sender_s,
        subject=subject_s,
    ):
        return "supplier_followup"

    subj_l = (subject_s or "").lower()
    snd_l = (sender_s or "").lower()
    source = row.get("source_file")

    if _is_sent_folder(source if isinstance(source, str) else None):
        if "cotiz" in subj_l or "quote" in subj_l or "presupuesto" in subj_l:
            return "quote_sent"
        return "waiting_client"

    if enrichment_available and _bool_signal(row.get("has_positive_signal")):
        if any(k in subj_l for k in _EQUIPMENT_KEYWORDS) or any(
            k in subj_l for k in ("licit", "equipo", "tender", "compra")
        ):
            return "client_opportunity"
        return "client_opportunity"

    if re.match(r"^re:\s", subj_l) or subj_l.startswith("re "):
        if "origenlab" in snd_l or is_internal_operator_contact(contact_email):
            return "waiting_supplier"
        return "client_response"

    if "cotiz" in subj_l or "presupuesto" in subj_l:
        return "waiting_supplier"

    if include_noise:
        return "client_response"
    return "client_response"


def role_category_to_legacy_storage(role: WarmCaseRoleCategory) -> WarmCaseLegacyCategory:
    """Map role category to Postgres/SQLite promotion CHECK values."""
    return {
        "client_opportunity": "opportunity",
        "client_response": "client_reply",
        "supplier_quote_received": "supplier_reply",
        "supplier_followup": "supplier_reply",
        "payment_admin": "client_reply",
        "logistics_admin": "client_reply",
        "internal_admin": "bounce",
        "system_noise": "bounce",
        "bounce_problem": "bounce",
        "deal_evidence_candidate": "client_reply",
        "quote_sent": "quote_sent",
        "waiting_supplier": "waiting_supplier",
        "waiting_client": "waiting_client",
    }[role]


def role_category_status(
    role: WarmCaseRoleCategory,
    row: dict[str, Any],
) -> Literal["new", "open", "waiting", "quoted", "problem"]:
    if role in ("bounce_problem", "system_noise", "internal_admin"):
        return "problem"
    if role == "quote_sent":
        return "quoted"
    if role in ("waiting_supplier", "waiting_client"):
        return "waiting"
    if role in (
        "client_opportunity",
        "payment_admin",
        "logistics_admin",
        "deal_evidence_candidate",
        "supplier_quote_received",
    ):
        return "open"
    if role == "supplier_followup":
        return "open"
    legacy = role_category_to_legacy_storage(role)
    if _bool_signal(row.get("has_suppression_signal")):
        if should_keep_visible_despite_suppression(
            _row_contact_email(row),
            _row_subject(row),
            category=legacy,
            snippet=row.get("snippet") if isinstance(row.get("snippet"), str) else None,
        ):
            return "open"
        return "problem"
    if _bool_signal(row.get("has_positive_signal")):
        return "open"
    return "new"


def role_category_next_action(role: WarmCaseRoleCategory) -> str:
    return {
        "bounce_problem": "Revisar NDR o rebote; no reenviar sin corregir dirección.",
        "system_noise": "Ignorar alerta de sistema/cuenta; no requiere acción comercial.",
        "internal_admin": "Nota interna de operador; no tratar como cliente ni proveedor.",
        "payment_admin": "Registrar/confirmar pago o datos bancarios; no cotizar.",
        "logistics_admin": "Revisar logística/cuenta de importación; no cotizar al remitente.",
        "deal_evidence_candidate": "Vincular al deal comercial; no cotizar desde este hilo.",
        "supplier_quote_received": "Cotización de proveedor recibida; vincular a oportunidad/cliente.",
        "supplier_followup": "Seguimiento con proveedor; leer propuesta y cerrar quote al cliente.",
        "quote_sent": "Confirmar si el cliente respondió; no duplicar cotización.",
        "waiting_client": "Esperar respuesta o seguimiento suave si pasó el plazo.",
        "waiting_supplier": "Seguimiento a proveedor por cotización pendiente.",
        "client_response": "Responder hilo comercial; verificar specs antes de cotizar.",
        "client_opportunity": "Priorizar según señal comercial; validar equipo y plazo.",
    }[role]
