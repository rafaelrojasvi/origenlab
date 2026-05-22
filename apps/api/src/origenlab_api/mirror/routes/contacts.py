"""Mirror mart contact list (read-only Postgres; not operator /contacts/{email})."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.mart_lists import (
    list_contacts as fetch_list_contacts,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    PaginatedContactsResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("", response_model=PaginatedContactsResponse)
def mirror_list_contacts(
    conn: MirrorDbConn,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    domain: str | None = Query(None, description="Exact domain filter"),
    q: str | None = Query(None, description="Search email, name, or org guess"),
    scope: Literal["canonical", "archive"] = Query(
        "canonical",
        description="canonical = mart.contact_master_canonical (default); archive = full mart.",
    ),
) -> PaginatedContactsResponse:
    """Paginated mart contact list (legacy parity; not Today contact detail)."""
    return fetch_list_contacts(
        conn, limit=limit, offset=offset, domain=domain, q=q, scope=scope
    )
