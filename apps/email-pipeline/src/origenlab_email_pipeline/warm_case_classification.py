"""Heuristic warm-case labels (read-only; shared by API and Postgres promotion)."""

from __future__ import annotations

import re
from typing import Any, Literal

from origenlab_email_pipeline.cases_review_queue import (
    commercial_hint_es,
    looks_like_obvious_noise,
)
from origenlab_email_pipeline.warm_case_sender_rules import (
    contact_email_from_sender,
    email_domain,
    is_real_client_domain,
    looks_like_client_oc_post_sale_subject,
    looks_like_payment_admin_contact,
    looks_like_security_notification,
    looks_like_supplier_marketing_thread,
    looks_like_vendor_logistics_contact,
    should_keep_visible_despite_suppression,
)

WarmCaseCategory = Literal[
    "client_reply",
    "supplier_reply",
    "quote_sent",
    "waiting_supplier",
    "waiting_client",
    "bounce",
    "opportunity",
]

WarmCaseStatus = Literal["new", "open", "waiting", "quoted", "problem"]

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


def account_name_from_sender(sender_preview: str | None, contact_email: str) -> str:
    if contact_email and "@" in contact_email:
        local, _, domain = contact_email.partition("@")
        if domain and not domain.endswith("origenlab.cl"):
            return domain.split(".")[0].title() or local
        return local
    s = (sender_preview or "").strip()
    if "<" in s:
        s = s.split("<", 1)[0].strip().strip('"')
    return s[:80] if s else "Desconocido"


def equipment_signal_text(subject: str, row: dict[str, Any], *, enrichment_available: bool) -> str:
    subj = subject.lower()
    for kw in _EQUIPMENT_KEYWORDS:
        if kw.lower() in subj:
            return kw
    hint = commercial_hint_es(row, enrichment_available=enrichment_available)
    if hint and hint != "—" and hint != "Sin señal CI":
        return hint[:120]
    return ""


def infer_warm_case_category(
    row: dict[str, Any],
    *,
    enrichment_available: bool,
    include_noise: bool,
) -> WarmCaseCategory:
    sender = row.get("sender_preview")
    subject = row.get("subject_preview")
    sender_s = sender if isinstance(sender, str) else None
    subject_s = subject if isinstance(subject, str) else None
    contact_email = contact_email_from_sender(sender_s)

    if looks_like_obvious_noise(sender_s, subject_s):
        return "bounce"

    if looks_like_security_notification(sender_s, subject_s, contact_email=contact_email):
        return "bounce"

    if looks_like_supplier_marketing_thread(
        contact_email=contact_email,
        sender=sender_s,
        subject=subject_s,
    ):
        return "supplier_reply"

    if looks_like_payment_admin_contact(contact_email, subject_s):
        return "client_reply"

    if looks_like_vendor_logistics_contact(contact_email, subject_s):
        return "client_reply"

    if is_real_client_domain(email_domain(contact_email)) and looks_like_client_oc_post_sale_subject(
        subject_s
    ):
        return "client_reply"

    subj_l = (subject_s or "").lower()
    snd_l = (sender_s or "").lower()
    source = row.get("source_file")

    if _is_sent_folder(source if isinstance(source, str) else None):
        if "cotiz" in subj_l or "quote" in subj_l or "presupuesto" in subj_l:
            return "quote_sent"
        return "waiting_client"

    if enrichment_available and _bool_signal(row.get("has_positive_signal")):
        if any(k in subj_l for k in ("licit", "equipo", "tender", "compra")):
            return "opportunity"
        return "opportunity"

    if re.match(r"^re:\s", subj_l) or subj_l.startswith("re "):
        if "origenlab" in snd_l:
            return "waiting_supplier"
        return "client_reply"

    if "cotiz" in subj_l or "presupuesto" in subj_l:
        return "waiting_supplier"

    if include_noise:
        return "client_reply"
    return "client_reply"


def infer_warm_case_status(category: WarmCaseCategory, row: dict[str, Any]) -> WarmCaseStatus:
    if category == "bounce":
        return "problem"
    if category == "quote_sent":
        return "quoted"
    if category in ("waiting_supplier", "waiting_client"):
        return "waiting"
    if category == "opportunity":
        return "open"
    if _bool_signal(row.get("has_suppression_signal")):
        if should_keep_visible_despite_suppression(
            contact_email_from_sender(
                row.get("sender_preview") if isinstance(row.get("sender_preview"), str) else None
            )
            or "",
            row.get("subject_preview") if isinstance(row.get("subject_preview"), str) else None,
            category=category,
        ):
            return "open"
        return "problem"
    if _bool_signal(row.get("has_positive_signal")):
        return "open"
    return "new"


def infer_next_action(category: WarmCaseCategory) -> str:
    return {
        "bounce": "Revisar NDR; no reenviar a la misma dirección sin corregir.",
        "quote_sent": "Confirmar si el cliente respondió; no duplicar cotización.",
        "waiting_client": "Esperar respuesta o seguimiento suave si pasó el plazo.",
        "waiting_supplier": "Seguimiento a proveedor por cotización pendiente.",
        "supplier_reply": "Leer adjunto/propuesta del proveedor y cerrar quote al cliente.",
        "client_reply": "Responder hilo comercial; verificar specs antes de cotizar.",
        "opportunity": "Priorizar según señal comercial; validar equipo y plazo.",
    }[category]
