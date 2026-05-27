"""Heuristic warm-case labels (read-only; shared by API and Postgres promotion)."""

from __future__ import annotations

from typing import Any, Literal

from origenlab_email_pipeline.cases_review_queue import commercial_hint_es
from origenlab_email_pipeline.warm_case_role_classification import (
    WarmCaseLegacyCategory,
    WarmCaseRoleCategory,
    infer_warm_case_role_category,
    role_category_next_action,
    role_category_status,
    role_category_to_legacy_storage,
)
from origenlab_email_pipeline.warm_case_sender_rules import contact_email_from_sender

# Legacy storage categories (Postgres CHECK / SQLite promotion).
WarmCaseCategory = WarmCaseLegacyCategory

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


def infer_warm_case_role(
    row: dict[str, Any],
    *,
    enrichment_available: bool,
    include_noise: bool,
) -> WarmCaseRoleCategory:
    return infer_warm_case_role_category(
        row,
        enrichment_available=enrichment_available,
        include_noise=include_noise,
    )


def infer_warm_case_category(
    row: dict[str, Any],
    *,
    enrichment_available: bool,
    include_noise: bool,
) -> WarmCaseCategory:
    role = infer_warm_case_role_category(
        row,
        enrichment_available=enrichment_available,
        include_noise=include_noise,
    )
    return role_category_to_legacy_storage(role)


def infer_warm_case_status(category: WarmCaseCategory, row: dict[str, Any]) -> WarmCaseStatus:
    role = infer_warm_case_role_category(
        row,
        enrichment_available=bool(row.get("has_positive_signal")),
        include_noise=True,
    )
    if role_category_to_legacy_storage(role) == category:
        return role_category_status(role, row)
    if category == "bounce":
        return "problem"
    if category == "quote_sent":
        return "quoted"
    if category in ("waiting_supplier", "waiting_client"):
        return "waiting"
    if category == "opportunity":
        return "open"
    return role_category_status(role, row)


def infer_next_action(category: WarmCaseCategory) -> str:
    legacy_to_role: dict[WarmCaseCategory, WarmCaseRoleCategory] = {
        "opportunity": "client_opportunity",
        "client_reply": "client_response",
        "supplier_reply": "supplier_followup",
        "quote_sent": "quote_sent",
        "waiting_supplier": "waiting_supplier",
        "waiting_client": "waiting_client",
        "bounce": "bounce_problem",
    }
    role = legacy_to_role.get(category, "client_response")
    return role_category_next_action(role)
