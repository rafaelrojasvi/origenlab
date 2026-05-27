"""Response-time warm-case normalization (read-only; no SQLite writes)."""

from __future__ import annotations

from origenlab_email_pipeline.warm_case_role_classification import (
    infer_warm_case_role_category,
    role_category_next_action,
    role_category_status,
)
from origenlab_api.schemas.cases import WarmCaseCategory, WarmCaseItem, WarmCaseStatus

ROLE_WARM_CATEGORIES: frozenset[str] = frozenset(
    {
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
        # Legacy API aliases (dashboard compat during 7B migration)
        "supplier_reply",
        "opportunity",
        "client_reply",
        "bounce",
        "auto_reply",
        "vendor_logistics",
    }
)

# Applied after normalization when positive_signal_only=True.
POST_NORMALIZE_POSITIVE_CATEGORIES: frozenset[str] = frozenset(
    {
        "client_opportunity",
        "client_response",
        "supplier_quote_received",
        "supplier_followup",
        "payment_admin",
        "logistics_admin",
        "deal_evidence_candidate",
        "quote_sent",
        "waiting_supplier",
        "waiting_client",
        # Legacy names still accepted from mirror rows until promotion catches up
        "client_reply",
        "supplier_reply",
        "opportunity",
        "vendor_logistics",
        "payment_admin",
    }
)

_HIDDEN_WITHOUT_NOISE: frozenset[str] = frozenset(
    {
        "system_noise",
        "internal_admin",
        "bounce_problem",
        "bounce",
        "auto_reply",
    }
)

_LEGACY_CATEGORY_ALIASES: dict[str, WarmCaseCategory] = {
    "vendor_logistics": "logistics_admin",
    "auto_reply": "system_noise",
    "bounce": "bounce_problem",
    "client_reply": "client_response",
    "supplier_reply": "supplier_followup",
    "opportunity": "client_opportunity",
}


def is_auto_reply_subject(subject: str | None) -> bool:
    sub = (subject or "").strip().lower()
    if not sub:
        return False
    if sub.startswith("automatic reply"):
        return True
    markers = (
        "automatic reply",
        "auto-reply",
        "out of office",
        "fuera de oficina",
        "respuesta automática",
        "respuesta automatica",
    )
    return any(marker in sub for marker in markers)


def _item_to_classifier_row(item: WarmCaseItem) -> dict[str, object]:
    return {
        "contact_email": item.contact_email,
        "sender_preview": item.contact_email,
        "subject_preview": item.subject,
        "snippet": item.snippet,
        "account_name": item.account_name,
        "has_positive_signal": item.category in ("opportunity", "client_opportunity"),
        "has_suppression_signal": item.status == "problem",
    }


def resolve_normalized_category(item: WarmCaseItem) -> WarmCaseCategory:
    """Role-level category from shared pipeline classifier."""
    role = infer_warm_case_role_category(
        _item_to_classifier_row(item),
        enrichment_available=item.category in ("opportunity", "client_opportunity"),
        include_noise=True,
    )
    if role in (
        "internal_admin",
        "system_noise",
        "payment_admin",
        "logistics_admin",
        "supplier_quote_received",
        "supplier_followup",
        "deal_evidence_candidate",
        "bounce_problem",
    ):
        return _canonical_category(role)
    if item.category in ("quote_sent", "waiting_supplier", "waiting_client"):
        return _canonical_category(item.category)
    return _canonical_category(role)


def _canonical_category(category: str) -> WarmCaseCategory:
    return _LEGACY_CATEGORY_ALIASES.get(category, category)  # type: ignore[return-value]


def normalize_warm_case_item(
    item: WarmCaseItem,
    *,
    include_noise: bool = False,
) -> WarmCaseItem | None:
    """
    Adjust category/status/next_action at response time.

    Returns None when the row should be omitted (noise/admin excluded).
    """
    category = _canonical_category(resolve_normalized_category(item))

    if is_auto_reply_subject(item.subject) and category not in (
        "supplier_quote_received",
        "supplier_followup",
    ):
        category = "system_noise"

    if category in _HIDDEN_WITHOUT_NOISE and not include_noise:
        return None

    status: WarmCaseStatus = role_category_status(
        category,  # type: ignore[arg-type]
        _item_to_classifier_row(item),
    )
    if category == "quote_sent":
        status = "quoted"
    elif category in ("waiting_supplier", "waiting_client"):
        status = "waiting"

    next_action = role_category_next_action(category)  # type: ignore[arg-type]

    return item.model_copy(
        update={
            "category": category,
            "status": status,
            "next_action": next_action,
        }
    )


def filter_positive_normalized_items(items: list[WarmCaseItem]) -> list[WarmCaseItem]:
    return [item for item in items if item.category in POST_NORMALIZE_POSITIVE_CATEGORIES]


def normalize_warm_case_items(
    items: list[WarmCaseItem],
    *,
    include_noise: bool = False,
    category_filter: str | None = None,
    positive_signal_only: bool = False,
) -> list[WarmCaseItem]:
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
