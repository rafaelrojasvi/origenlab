"""Mart organizations (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from origenlab_api.deps import DbConn
from origenlab_api.schemas import PaginatedOrganizationsResponse
from origenlab_api.services import queries

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=PaginatedOrganizationsResponse)
def list_organizations(
    conn: DbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    domain: str | None = Query(None, description="Exact domain filter"),
    q: str | None = Query(None, description="Search domain or organization name"),
) -> PaginatedOrganizationsResponse:
    return queries.list_organizations(
        conn, limit=limit, offset=offset, domain=domain, q=q
    )
