"""Read-only redacted product catalogue (Postgres catalog.* mirror)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    CATALOG_MIRROR_PROSE_FIELDS,
    assert_mirror_text_safe,
    prepare_catalog_mirror_text,
)
from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import DEFAULT_MAX_LIMIT
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    CATALOG_DISCLAIMER,
    CatalogCommercialLinkRow,
    CatalogPriceSnapshotRow,
    CatalogProductAliasRow,
    CatalogProductCategoryRow,
    CatalogProductDetail,
    CatalogProductDetailResponse,
    CatalogProductListItem,
    CatalogProductSpecRow,
    CatalogProductsListResponse,
    CatalogSupplierOfferRow,
)

CATALOG_PRODUCT_TABLE = ("catalog", "product")

_PRODUCT_LIST_SELECT = """
SELECT
  p.product_key, p.display_name, p.brand, p.product_kind, p.equipment_class,
  p.model_number, p.public_summary, p.confidence
FROM catalog.product p
"""

_PRODUCT_DETAIL_SELECT = """
SELECT
  product_key, display_name, brand, manufacturer_name, product_kind,
  equipment_class, model_number, default_unit, website_slug, website_product_id,
  public_summary, is_active, confidence
FROM catalog.product
WHERE product_key = %s
LIMIT 1
"""


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _sanitize_row_strings(row: dict[str, Any], *, prefix: str) -> None:
    for key, value in row.items():
        if not isinstance(value, str):
            continue
        field = f"{prefix}.{key}"
        if key in CATALOG_MIRROR_PROSE_FIELDS:
            row[key] = prepare_catalog_mirror_text(value, field=field)
        else:
            assert_mirror_text_safe(value, field=field)


def _build_list_filters(
    *,
    q: str | None,
    brand: str | None,
    equipment_class: str | None,
    category_key: str | None,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(
            "("
            "p.display_name ILIKE %s OR p.product_key ILIKE %s "
            "OR COALESCE(p.brand, '') ILIKE %s OR COALESCE(p.public_summary, '') ILIKE %s"
            ")"
        )
        params.extend([pattern, pattern, pattern, pattern])
    if brand and brand.strip():
        conditions.append("COALESCE(p.brand, '') ILIKE %s")
        params.append(brand.strip())
    if equipment_class and equipment_class.strip():
        conditions.append("p.equipment_class = %s")
        params.append(equipment_class.strip())
    if category_key and category_key.strip():
        conditions.append(
            "EXISTS ("
            "SELECT 1 FROM catalog.product_category_map m "
            "WHERE m.product_key = p.product_key AND m.category_key = %s"
            ")"
        )
        params.append(category_key.strip())
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


def list_catalog_products(
    conn: Connection,
    *,
    q: str | None = None,
    brand: str | None = None,
    equipment_class: str | None = None,
    category_key: str | None = None,
    limit: int = 50,
) -> CatalogProductsListResponse:
    limit = _clamp_limit(limit)
    schema, table = CATALOG_PRODUCT_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return CatalogProductsListResponse(
            table_available=False,
            items=[],
            total=0,
            limit=limit,
        )

    where, filter_params = _build_list_filters(
        q=q, brand=brand, equipment_class=equipment_class, category_key=category_key
    )
    count_sql = f"SELECT COUNT(*)::bigint AS n FROM catalog.product p{where}"
    count_row = conn.execute(count_sql, tuple(filter_params)).fetchone()
    total = int((count_row or {}).get("n") or 0)

    list_sql = (
        _PRODUCT_LIST_SELECT
        + where
        + " ORDER BY p.display_name ASC, p.product_key ASC LIMIT %s"
    )
    rows = fetch_all(conn, list_sql, tuple(filter_params + [limit]))
    items: list[CatalogProductListItem] = []
    for row in rows:
        _sanitize_row_strings(row, prefix="product")
        items.append(CatalogProductListItem.model_validate(row))

    return CatalogProductsListResponse(
        table_available=True,
        items=items,
        total=total,
        limit=limit,
        disclaimer=CATALOG_DISCLAIMER,
    )


def _load_aliases(conn: Connection, product_key: str) -> list[CatalogProductAliasRow]:
    rows = fetch_all(
        conn,
        """
        SELECT alias_source, alias_code, alias_kind
        FROM catalog.product_alias
        WHERE product_key = %s
        ORDER BY alias_source, alias_code
        """,
        (product_key,),
    )
    out: list[CatalogProductAliasRow] = []
    for row in rows:
        _sanitize_row_strings(row, prefix="alias")
        out.append(CatalogProductAliasRow.model_validate(row))
    return out


def _load_categories(conn: Connection, product_key: str) -> list[CatalogProductCategoryRow]:
    rows = fetch_all(
        conn,
        """
        SELECT c.category_key, c.display_name, c.equipment_class, m.is_primary
        FROM catalog.product_category_map m
        JOIN catalog.product_category c ON c.category_key = m.category_key
        WHERE m.product_key = %s
        ORDER BY m.is_primary DESC, c.display_name
        """,
        (product_key,),
    )
    out: list[CatalogProductCategoryRow] = []
    for row in rows:
        payload = dict(row)
        payload["is_primary"] = bool(payload.get("is_primary"))
        _sanitize_row_strings(payload, prefix="category")
        out.append(CatalogProductCategoryRow.model_validate(payload))
    return out


def _load_specs(conn: Connection, product_key: str) -> list[CatalogProductSpecRow]:
    rows = fetch_all(
        conn,
        """
        SELECT spec_group, spec_key, spec_value, spec_value_numeric, spec_unit, source, confidence
        FROM catalog.product_spec
        WHERE product_key = %s
        ORDER BY spec_group NULLS LAST, spec_key
        """,
        (product_key,),
    )
    out: list[CatalogProductSpecRow] = []
    for row in rows:
        _sanitize_row_strings(row, prefix="spec")
        out.append(CatalogProductSpecRow.model_validate(row))
    return out


def _load_supplier_offers(conn: Connection, product_key: str) -> list[CatalogSupplierOfferRow]:
    rows = fetch_all(
        conn,
        """
        SELECT
          offer_key, supplier_org_name, supplier_domain, offer_status,
          quoted_at, valid_until, incoterm, payment_terms, delivery_terms,
          currency, quantity_offered, availability_note, confidence
        FROM catalog.supplier_offer
        WHERE product_key = %s
        ORDER BY offer_key
        """,
        (product_key,),
    )
    out: list[CatalogSupplierOfferRow] = []
    for row in rows:
        _sanitize_row_strings(row, prefix="supplier_offer")
        out.append(CatalogSupplierOfferRow.model_validate(row))
    return out


def _load_price_snapshots(conn: Connection, product_key: str) -> list[CatalogPriceSnapshotRow]:
    rows = fetch_all(
        conn,
        """
        SELECT
          snapshot_key, snapshot_kind, offer_key, currency, amount_decimal, amount_minor,
          amount_clp_integer, quantity, unit, incoterm, price_notes, is_public_safe,
          confidence, observed_at
        FROM catalog.price_snapshot
        WHERE product_key = %s
        ORDER BY observed_at DESC NULLS LAST, snapshot_key
        """,
        (product_key,),
    )
    out: list[CatalogPriceSnapshotRow] = []
    for row in rows:
        payload = dict(row)
        payload["is_public_safe"] = bool(payload.get("is_public_safe"))
        _sanitize_row_strings(payload, prefix="price_snapshot")
        out.append(CatalogPriceSnapshotRow.model_validate(payload))
    return out


def _load_commercial_links(conn: Connection, product_key: str) -> list[CatalogCommercialLinkRow]:
    rows = fetch_all(
        conn,
        """
        SELECT link_kind, link_ref, confidence
        FROM catalog.product_commercial_link
        WHERE product_key = %s
        ORDER BY link_kind, link_ref
        """,
        (product_key,),
    )
    out: list[CatalogCommercialLinkRow] = []
    for row in rows:
        _sanitize_row_strings(row, prefix="commercial_link")
        out.append(CatalogCommercialLinkRow.model_validate(row))
    return out


def get_catalog_product(
    conn: Connection,
    *,
    product_key: str,
) -> CatalogProductDetailResponse:
    schema, table = CATALOG_PRODUCT_TABLE
    if not table_exists(conn, schema=schema, table=table):
        return CatalogProductDetailResponse(table_available=False, product=None)

    row = fetch_one(conn, _PRODUCT_DETAIL_SELECT, (product_key.strip(),))
    if not row:
        return CatalogProductDetailResponse(table_available=True, product=None)

    payload = dict(row)
    payload["is_active"] = bool(payload.get("is_active"))
    _sanitize_row_strings(payload, prefix="product")
    key = str(payload["product_key"])

    detail = CatalogProductDetail(
        **payload,
        aliases=_load_aliases(conn, key),
        categories=_load_categories(conn, key),
        specs=_load_specs(conn, key),
        supplier_offers=_load_supplier_offers(conn, key),
        price_snapshots=_load_price_snapshots(conn, key),
        commercial_links=_load_commercial_links(conn, key),
    )
    return CatalogProductDetailResponse(
        table_available=True,
        product=detail,
        disclaimer=CATALOG_DISCLAIMER,
    )
