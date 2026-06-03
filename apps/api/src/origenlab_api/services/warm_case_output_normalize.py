"""Response-time warm-case normalization (read-only; no SQLite writes)."""

from __future__ import annotations

import re

from origenlab_email_pipeline.warm_case_grouping import warm_case_group_key
from origenlab_email_pipeline.warm_case_role_classification import (
    infer_warm_case_role_category,
    role_category_next_action,
    role_category_status,
)
from origenlab_email_pipeline.warm_case_sender_rules import (
    looks_like_auto_reply_text,
    looks_like_cyberday_bulk_campaign_subject,
    looks_like_real_supplier_quote_content,
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
        "campaign_outreach",
        "waiting_campaign_reply",
        "auto_acknowledgement",
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
        "auto_acknowledgement",
        "campaign_outreach",
        "waiting_campaign_reply",
    }
)

_LEGACY_CATEGORY_ALIASES: dict[str, WarmCaseCategory] = {
    "vendor_logistics": "logistics_admin",
    "auto_reply": "system_noise",
    "bounce": "bounce_problem",
    "client_reply": "client_response",
    "supplier_reply": "supplier_followup",
    "opportunity": "client_opportunity",
    "waiting_client": "waiting_client",
}

_SENSITIVE_PREVIEW_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b"),
    re.compile(r"\b(?:swift|iban|beneficiario|titular|cuenta(?:\s+corriente)?)\b[^.,;]{0,80}", re.I),
    re.compile(r"\b\d{10,}\b"),
)


def redact_sensitive_preview(value: str) -> str:
    out = value
    for pattern in _SENSITIVE_PREVIEW_PATTERNS:
        out = pattern.sub("[oculto]", out)
    return out


def is_auto_reply_subject(subject: str | None) -> bool:
    """Subject-only autoreply check (tests + legacy callers)."""
    return looks_like_auto_reply_text(subject, None)


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
    if looks_like_cyberday_bulk_campaign_subject(item.subject):
        return _canonical_category("campaign_outreach")
    if looks_like_idiem_auto_ack(item):
        return _canonical_category("auto_acknowledgement")

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


def looks_like_idiem_auto_ack(item: WarmCaseItem) -> bool:
    from origenlab_email_pipeline.warm_case_sender_rules import looks_like_idiem_auto_acknowledgement

    return looks_like_idiem_auto_acknowledgement(
        item.contact_email,
        item.subject,
        snippet=item.snippet,
        sender=item.contact_email,
    )


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

    if looks_like_auto_reply_text(item.subject, item.snippet):
        if not looks_like_real_supplier_quote_content(item.subject, item.snippet):
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
    existing_next = (item.next_action or "").strip()
    if existing_next and ("rv10.70" in existing_next.lower() or "crtop" in existing_next.lower()):
        next_action = existing_next

    safe_snippet = redact_sensitive_preview(item.snippet or "")

    return item.model_copy(
        update={
            "category": category,
            "status": status,
            "next_action": next_action,
            "snippet": safe_snippet,
        }
    )


def filter_positive_normalized_items(items: list[WarmCaseItem]) -> list[WarmCaseItem]:
    return [item for item in items if item.category in POST_NORMALIZE_POSITIVE_CATEGORIES]


def dedupe_warm_case_items(items: list[WarmCaseItem]) -> list[WarmCaseItem]:
    """Collapse duplicate supplier/thread rows; keep latest activity and grouped count."""
    buckets: dict[str, list[WarmCaseItem]] = {}
    for item in items:
        key = warm_case_group_key(item.contact_email, item.subject)
        buckets.setdefault(key, []).append(item)

    merged: list[WarmCaseItem] = []
    for group in buckets.values():
        group.sort(
            key=lambda row: (row.last_seen_at or "", row.last_email_id),
            reverse=True,
        )
        primary = group[0]
        count = len(group)
        if count > 1:
            primary = primary.model_copy(update={"grouped_email_count": count})
        merged.append(primary)

    merged.sort(
        key=lambda row: (row.last_seen_at or "", row.last_email_id),
        reverse=True,
    )
    return merged


def normalize_warm_case_items(
    items: list[WarmCaseItem],
    *,
    include_noise: bool = False,
    category_filter: str | None = None,
    positive_signal_only: bool = False,
) -> list[WarmCaseItem]:
    needle = (category_filter or "").strip().lower()
    if needle:
        needle = _LEGACY_CATEGORY_ALIASES.get(needle, needle)
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
    return dedupe_warm_case_items(out)
