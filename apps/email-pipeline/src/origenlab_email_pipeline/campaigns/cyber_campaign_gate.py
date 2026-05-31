"""Gate and product-angle helpers for Cyber campaign (read-only)."""

from __future__ import annotations

from typing import Any

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_INVALID_EMAIL,
    evaluate_export_eligibility,
    normalize_export_email,
)
from origenlab_email_pipeline.campaigns.cyber_campaign_types import (
    SAFETY_BLOCKED,
    SAFETY_ELIGIBLE,
    SAFETY_SAME_DOMAIN,
)

_EXCLUSION_REASON_ES: dict[str, str] = {
    "invalid_email": "correo inválido",
    "suppression": "supresión / lista de no contactar",
    "domain_suppression": "dominio suprimido",
    "sent_history": "ya contactado en carpeta Enviados",
    "outreach_contacted": "estado outreach: contactado",
    "outreach_replied": "estado outreach: respondió",
    "outreach_snoozed": "estado outreach: pospuesto",
    "supplier_domain": "dominio de proveedor",
    "noise_email": "correo ruido (noreply/admin)",
    "noise_organization": "organización ruido",
    "internal_domain": "dominio interno OrigenLab",
}


def exclusion_reason_es(code: str) -> str:
    return _EXCLUSION_REASON_ES.get(code, code.replace("_", " "))


def product_angle(
    *,
    quote_count: int = 0,
    purchase_count: int = 0,
    equipment_hint: str = "",
    fit_bucket: str = "",
) -> str:
    if equipment_hint.strip():
        return equipment_hint.strip()[:200]
    if quote_count > 0:
        return "Equipos de laboratorio con historial de cotización — beneficio Cyber en línea seleccionada"
    if purchase_count > 0:
        return "Reposición / ampliación de equipos con relación comercial previa"
    if fit_bucket in ("high_fit", "medium_fit"):
        return "Laboratorio / institución con encaje comercial — equipos seleccionados Cyber"
    return "Equipos de laboratorio seleccionados — mejora comercial Cyber (sujeta a confirmación)"


def classify_safety(
    email: str,
    organization: str | None,
    *,
    gate_ctx: Any,
    universe_ctx: Any,
) -> tuple[str, str]:
    em = normalize_export_email(email) or ""
    dom = domain_of(em) or ""
    if (
        dom
        and dom in universe_ctx.domains_with_sent_contact
        and em not in universe_ctx.gate.sent_recipient_norms
    ):
        return SAFETY_SAME_DOMAIN, "mismo dominio ya contactado con otro correo"

    gate = evaluate_export_eligibility(
        contact_email=em,
        institution_name=organization,
        ctx=gate_ctx,
    )
    if gate.eligible:
        return SAFETY_ELIGIBLE, ""
    code = gate.reasons[0] if gate.reasons else REASON_INVALID_EMAIL
    return SAFETY_BLOCKED, exclusion_reason_es(code)
