"""Operator status (SQLite read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from origenlab_api.schemas.operator import OperatorStatusResponse
from origenlab_api.services.operator_status_service import build_operator_status_response
from origenlab_api.settings import Settings, get_settings

router = APIRouter(prefix="/operator", tags=["operator"])


@router.get("/status", response_model=OperatorStatusResponse)
def operator_status(
    settings: Settings = Depends(get_settings),
    max_staleness_days: float = Query(14.0, ge=1.0, le=365.0),
) -> OperatorStatusResponse:
    return build_operator_status_response(
        settings,
        max_staleness_days=max_staleness_days,
    )
