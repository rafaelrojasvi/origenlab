"""Mirror commercial purchase events (read-only Postgres reporting)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.commercial_purchase import (
    get_commercial_purchase_event,
    list_commercial_purchase_events,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    CommercialPurchaseEventDetailResponse,
    CommercialPurchaseEventsListResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("/purchase-events", response_model=CommercialPurchaseEventsListResponse)
def mirror_list_purchase_events(
    conn: MirrorDbConn,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CommercialPurchaseEventsListResponse:
    """Recent confirmed purchase orders (Postgres mirror; not Today warm cases)."""
    return list_commercial_purchase_events(conn, limit=limit)


@router.get(
    "/purchase-events/{event_id}",
    response_model=CommercialPurchaseEventDetailResponse,
)
def mirror_get_purchase_event(
    conn: MirrorDbConn,
    event_id: int,
) -> CommercialPurchaseEventDetailResponse:
    detail = get_commercial_purchase_event(conn, event_id=event_id)
    if detail.event is None and detail.table_available:
        raise HTTPException(status_code=404, detail="purchase event not found")
    return detail
