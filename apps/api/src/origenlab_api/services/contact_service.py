"""Contact detail service (repository-backed)."""

from __future__ import annotations

from origenlab_api.backends.factory import RepositoryBundle, get_repository_bundle
from origenlab_api.schemas.contacts import (
    ContactDetailResponse,
    ContactMeta,
    ContactOutreach,
    ContactProfile,
    ContactSentHistory,
)
from origenlab_api.settings import Settings


def build_contact_detail_response(
    settings: Settings,
    email: str,
    *,
    repos: RepositoryBundle | None = None,
) -> ContactDetailResponse:
    bundle = repos or get_repository_bundle(settings)
    result = bundle.contact.get_contact_detail(email)
    note = "; ".join(result.warnings[:3]) if result.warnings else ""
    if len(result.warnings) > 3:
        note += f" (+{len(result.warnings) - 3} more warnings)"
    return ContactDetailResponse(
        meta=ContactMeta(
            data_source=result.data_source,
            read_only=True,
            reduced_mode=result.reduced_mode,
            note=note,
        ),
        contact=ContactProfile.model_validate(result.contact),
        outreach=ContactOutreach.model_validate(result.outreach),
        sent_history=ContactSentHistory.model_validate(result.sent_history),
        warnings=result.warnings,
    )
