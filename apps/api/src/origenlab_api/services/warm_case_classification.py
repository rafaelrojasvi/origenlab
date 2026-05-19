"""Heuristic warm-case labels (read-only; no ML)."""

from __future__ import annotations

import re
from typing import Any

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.cases_review_queue import (
    commercial_hint_es,
    looks_like_obvious_noise,
)

from origenlab_api.schemas.cases import WarmCaseCategory, WarmCaseItem, WarmCaseStatus

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

_SUPPLIER_HINTS = (
    "supplier",
    "proveedor",
    "distrib",
    "hielscher",
    "ortoalresa",
    "serva.de",
    "ollital",
    "kern",
    "sartorius",
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


def _contact_email_from_sender(sender_preview: str | None) -> str:
    found = emails_in(sender_preview or "")
    return found[0] if found else ""


def _account_name(sender_preview: str | None, contact_email: str) -> str:
    if contact_email and "@" in contact_email:
        local, _, domain = contact_email.partition("@")
        if domain and not domain.endswith("origenlab.cl"):
            return domain.split(".")[0].title() or local
        return local
    s = (sender_preview or "").strip()
    if "<" in s:
        s = s.split("<", 1)[0].strip().strip('"')
    return s[:80] if s else "Desconocido"


def _equipment_signal(subject: str, row: dict[str, Any], *, enrichment_available: bool) -> str:
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
    if looks_like_obvious_noise(
        sender if isinstance(sender, str) else None,
        subject if isinstance(subject, str) else None,
    ):
        return "bounce"

    subj_l = (subject or "").lower() if isinstance(subject, str) else ""
    snd_l = (sender or "").lower() if isinstance(sender, str) else ""
    source = row.get("source_file")

    if _is_sent_folder(source if isinstance(source, str) else None):
        if "cotiz" in subj_l or "quote" in subj_l or "presupuesto" in subj_l:
            return "quote_sent"
        return "waiting_client"

    if enrichment_available and _bool_signal(row.get("has_positive_signal")):
        if any(k in subj_l for k in ("licit", "equipo", "tender", "compra")):
            return "opportunity"
        return "opportunity"

    if any(h in snd_l or h in subj_l for h in _SUPPLIER_HINTS):
        return "supplier_reply"

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


def row_to_warm_case_item(
    row: dict[str, Any],
    *,
    enrichment_available: bool,
    include_noise: bool,
) -> tuple[WarmCaseItem, WarmCaseCategory]:
    email_id = int(row["email_id"])
    subject = str(row.get("subject_preview") or "")
    sender = str(row.get("sender_preview") or "")
    category = infer_warm_case_category(
        row,
        enrichment_available=enrichment_available,
        include_noise=include_noise,
    )
    status = infer_warm_case_status(category, row)
    contact_email = _contact_email_from_sender(sender)
    snippet_parts = [p for p in (subject.strip(), sender.strip()) if p]
    snippet = " · ".join(snippet_parts)[:280]

    item = WarmCaseItem(
        case_id=f"gmail-contacto-{email_id}",
        last_email_id=email_id,
        last_seen_at=row.get("date_iso") if isinstance(row.get("date_iso"), str) else None,
        account_name=_account_name(sender, contact_email),
        contact_email=contact_email,
        subject=subject,
        category=category,
        status=status,
        next_action=infer_next_action(category),
        equipment_signal=_equipment_signal(subject, row, enrichment_available=enrichment_available),
        snippet=snippet,
        gmail_url=None,
    )
    return item, category
