"""Heuristic warm-case labels (read-only; no ML)."""

from __future__ import annotations

from typing import Any

from origenlab_email_pipeline.warm_case_classification import (
    account_name_from_sender as _account_name,
    contact_email_from_sender as _contact_email_from_sender,
    equipment_signal_text as _equipment_signal,
    infer_next_action,
    infer_warm_case_category,
    infer_warm_case_status,
)

from origenlab_api.schemas.cases import WarmCaseCategory, WarmCaseItem, WarmCaseStatus

# Re-export shared heuristics from email-pipeline (DB-2B promotion uses the same module).
__all__ = [
    "infer_warm_case_category",
    "infer_warm_case_status",
    "infer_next_action",
    "row_to_warm_case_item",
]


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
