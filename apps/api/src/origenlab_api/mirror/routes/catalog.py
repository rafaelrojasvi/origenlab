"""Mirror product catalogue (read-only Postgres catalog.*)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from origenlab_api.mirror.deps import MirrorDbConn
from origenlab_email_pipeline.postgres_dashboard_api.catalog import (
    get_catalog_product,
    list_catalog_products,
)
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    CatalogProductDetailResponse,
    CatalogProductsListResponse,
)

router = APIRouter(tags=["postgres-mirror"])


@router.get("/products", response_model=CatalogProductsListResponse)
def mirror_list_catalog_products(
    conn: MirrorDbConn,
    q: Annotated[str | None, Query(max_length=200)] = None,
    brand: Annotated[str | None, Query(max_length=120)] = None,
    equipment_class: Annotated[str | None, Query(max_length=80)] = None,
    category_key: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CatalogProductsListResponse:
    """Redacted product catalogue list (Postgres mirror; SQLite is source of truth)."""
    return list_catalog_products(
        conn,
        q=q,
        brand=brand,
        equipment_class=equipment_class,
        category_key=category_key,
        limit=limit,
    )


@router.get("/products/{product_key}", response_model=CatalogProductDetailResponse)
def mirror_get_catalog_product(
    conn: MirrorDbConn,
    product_key: str,
) -> CatalogProductDetailResponse:
    detail = get_catalog_product(conn, product_key=product_key)
    if detail.product is None and detail.table_available:
        raise HTTPException(status_code=404, detail="catalog product not found")
    return detail
