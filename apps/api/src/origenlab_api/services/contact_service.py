"""Contact detail service (read-only)."""

from __future__ import annotations

from origenlab_api.repositories.contact import fetch_contact_intelligence
from origenlab_api.schemas.contacts import (
    ContactDetailResponse,
    ContactMeta,
    ContactOutreach,
    ContactProfile,
    ContactSentHistory,
)
from origenlab_api.settings import Settings


def build_contact_detail_response(settings: Settings, email: str) -> ContactDetailResponse:
    sqlite_path = settings.resolved_sqlite_path()
    active_current = settings.resolved_active_current()
    contact, outreach, sent, warnings, reduced_mode = fetch_contact_intelligence(
        sqlite_path,
        active_current,
        email,
    )
    note = "; ".join(warnings[:3]) if warnings else ""
    if len(warnings) > 3:
        note += f" (+{len(warnings) - 3} more warnings)"
    return ContactDetailResponse(
        meta=ContactMeta(reduced_mode=reduced_mode, note=note),
        contact=ContactProfile.model_validate(contact),
        outreach=ContactOutreach.model_validate(outreach),
        sent_history=ContactSentHistory.model_validate(sent),
        warnings=warnings,
    )
