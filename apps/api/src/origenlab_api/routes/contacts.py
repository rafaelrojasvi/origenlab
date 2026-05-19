"""Contact intelligence (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from origenlab_api.schemas.contacts import ContactDetailResponse
from origenlab_api.services.contact_service import build_contact_detail_response
from origenlab_api.settings import Settings, get_settings

router = APIRouter(tags=["contacts"])


@router.get("/contacts/{email}", response_model=ContactDetailResponse)
def contact_detail(
    email: str,
    settings: Settings = Depends(get_settings),
) -> ContactDetailResponse:
    try:
        return build_contact_detail_response(settings, email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
