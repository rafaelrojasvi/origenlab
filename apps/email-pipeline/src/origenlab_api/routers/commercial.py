"""Read-only confirmed purchase order events (Postgres mirror)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from origenlab_api.deps import DbConn
from origenlab_api.schemas import (
    CommercialPurchaseEventDetailResponse,
    CommercialPurchaseEventsListResponse,
)
from origenlab_api.services import queries

router = APIRouter(prefix="/commercial", tags=["commercial"])


@router.get("/purchase-events", response_model=CommercialPurchaseEventsListResponse)
def list_purchase_events(
    conn: DbConn,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CommercialPurchaseEventsListResponse:
    """Recent confirmed purchase orders promoted from SQLite."""
    return queries.list_commercial_purchase_events(conn, limit=limit)


@router.get("/purchase-events/{event_id}", response_model=CommercialPurchaseEventDetailResponse)
def get_purchase_event(
    conn: DbConn,
    event_id: int,
) -> CommercialPurchaseEventDetailResponse:
    """Single confirmed purchase order with line items."""
    detail = queries.get_commercial_purchase_event(conn, event_id=event_id)
    if detail.event is None and detail.table_available:
        raise HTTPException(status_code=404, detail="purchase event not found")
    return detail
