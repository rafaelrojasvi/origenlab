"""Mirror mart organization list (read-only Postgres)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.mart_lists import (
    list_organizations as fetch_list_organizations,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    PaginatedOrganizationsResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("", response_model=PaginatedOrganizationsResponse)
def mirror_list_organizations(
    conn: MirrorDbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    domain: str | None = Query(None, description="Exact domain filter"),
    q: str | None = Query(None, description="Search domain or organization name"),
    scope: Literal["canonical", "archive"] = Query(
        "canonical",
        description=(
            "canonical = mart.organization_master_canonical (default); "
            "archive = full mart."
        ),
    ),
) -> PaginatedOrganizationsResponse:
    return fetch_list_organizations(
        conn, limit=limit, offset=offset, domain=domain, q=q, scope=scope
    )
