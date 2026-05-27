"""Mirror lead research prospects (read-only Postgres lead_intel.*)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.lead_intel import (
    get_lead_prospect,
    get_lead_research_summary,
    list_lead_prospects,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    LeadProspectDetailResponse,
    LeadProspectsListResponse,
    LeadResearchSummaryResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("/prospects", response_model=LeadProspectsListResponse)
def mirror_list_lead_prospects(
    conn: MirrorDbConn,
    q: Annotated[str | None, Query(max_length=200)] = None,
    classification: Annotated[str | None, Query(max_length=80)] = None,
    sector: Annotated[str | None, Query(max_length=120)] = None,
    region: Annotated[str | None, Query(max_length=120)] = None,
    buyer_type: Annotated[str | None, Query(max_length=80)] = None,
    campaign_bucket: Annotated[str | None, Query(max_length=80)] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    include_blocked: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LeadProspectsListResponse:
    return list_lead_prospects(
        conn,
        q=q,
        classification=classification,
        sector=sector,
        region=region,
        buyer_type=buyer_type,
        campaign_bucket=campaign_bucket,
        min_score=min_score,
        include_blocked=include_blocked,
        limit=limit,
    )


@router.get("/prospects/{prospect_key}", response_model=LeadProspectDetailResponse)
def mirror_get_lead_prospect(
    conn: MirrorDbConn,
    prospect_key: str,
) -> LeadProspectDetailResponse:
    detail = get_lead_prospect(conn, prospect_key=prospect_key)
    if detail.prospect is None and detail.table_available:
        raise HTTPException(status_code=404, detail="prospect not found")
    return detail


@router.get("/summary", response_model=LeadResearchSummaryResponse)
def mirror_lead_research_summary(conn: MirrorDbConn) -> LeadResearchSummaryResponse:
    return get_lead_research_summary(conn)
