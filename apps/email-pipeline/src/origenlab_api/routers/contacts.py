"""Mart contacts (read-only)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from origenlab_api.deps import DbConn
from origenlab_api.schemas import PaginatedContactsResponse
from origenlab_api.services import queries

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=PaginatedContactsResponse)
def list_contacts(
    conn: DbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    domain: str | None = Query(None, description="Exact domain filter"),
    q: str | None = Query(None, description="Search email, name, or org guess"),
    scope: Literal["canonical", "archive"] = Query(
        "canonical",
        description="canonical = mart.contact_master_canonical (default); archive = full mart.",
    ),
) -> PaginatedContactsResponse:
    return queries.list_contacts(
        conn, limit=limit, offset=offset, domain=domain, q=q, scope=scope
    )
