"""Build redacted catalog rows from SQLite for Postgres mirror."""

from __future__ import annotations

import sqlite3
from typing import Any

from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    CatalogMirrorSafetyError,
    assert_mirror_row_safe,
    assert_mirror_text_safe,
)
from origenlab_email_pipeline.catalog.catalog_schema import catalog_tables_exist


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row)))


def _bool_from_sqlite(value: Any) -> bool:
    return bool(int(value or 0))


def load_catalog_mirror_payload(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Load all catalog mirror tables from SQLite (read-only, redacted columns only)."""
    if not catalog_tables_exist(conn):
        return {
            "products": [],
            "categories": [],
            "aliases": [],
            "category_maps": [],
            "specs": [],
            "supplier_offers": [],
            "price_snapshots": [],
            "commercial_links": [],
            "commercial_history": [],
        }

    products: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT product_key, display_name, brand, manufacturer_name, product_kind,
               equipment_class, model_number, default_unit, website_slug,
               website_product_id, public_summary, is_active, confidence
        FROM catalog_product
        ORDER BY product_key
        """
    ):
        d = _row_dict(row)
        d["is_active"] = _bool_from_sqlite(d.get("is_active"))
        assert_mirror_row_safe(d, table="product")
        products.append(d)

    categories: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT category_key, parent_category_key, display_name, equipment_class
        FROM catalog_product_category
        ORDER BY category_key
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="product_category")
        categories.append(d)

    aliases: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.product_key, a.alias_code, a.alias_source, a.alias_kind
        FROM catalog_product_alias a
        JOIN catalog_product p ON p.id = a.product_id
        ORDER BY a.alias_source, a.alias_code
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="product_alias")
        aliases.append(d)

    category_maps: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.product_key, c.category_key, m.is_primary
        FROM catalog_product_category_map m
        JOIN catalog_product p ON p.id = m.product_id
        JOIN catalog_product_category c ON c.id = m.category_id
        ORDER BY p.product_key, c.category_key
        """
    ):
        d = _row_dict(row)
        d["is_primary"] = _bool_from_sqlite(d.get("is_primary"))
        assert_mirror_row_safe(d, table="product_category_map")
        category_maps.append(d)

    specs: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.product_key, s.spec_group, s.spec_key, s.spec_value, s.spec_value_numeric,
               s.spec_unit, s.source, s.confidence
        FROM catalog_product_spec s
        JOIN catalog_product p ON p.id = s.product_id
        ORDER BY p.product_key, s.spec_key, s.source
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="product_spec")
        specs.append(d)

    supplier_offers: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT o.offer_key, p.product_key, o.supplier_org_name, o.supplier_domain,
               o.offer_status, o.quoted_at, o.valid_until, o.incoterm, o.payment_terms,
               o.delivery_terms, o.currency, o.quantity_offered, o.availability_note,
               o.confidence
        FROM catalog_supplier_offer o
        JOIN catalog_product p ON p.id = o.product_id
        ORDER BY o.offer_key
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="supplier_offer")
        supplier_offers.append(d)

    price_snapshots: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT ps.snapshot_key, p.product_key, o.offer_key,
               ps.snapshot_kind, ps.currency, ps.amount_decimal, ps.amount_minor,
               ps.amount_clp_integer, ps.quantity, ps.unit, ps.incoterm, ps.price_notes,
               ps.is_public_safe, ps.confidence, ps.observed_at
        FROM catalog_price_snapshot ps
        JOIN catalog_product p ON p.id = ps.product_id
        LEFT JOIN catalog_supplier_offer o ON o.id = ps.supplier_offer_id
        ORDER BY ps.snapshot_key
        """
    ):
        d = _row_dict(row)
        d["is_public_safe"] = _bool_from_sqlite(d.get("is_public_safe"))
        assert_mirror_row_safe(d, table="price_snapshot")
        if d["is_public_safe"]:
            raise CatalogMirrorSafetyError(
                f"price_snapshot {d['snapshot_key']}: is_public_safe must be false in v1"
            )
        price_snapshots.append(d)

    commercial_links: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.product_key, l.link_kind, l.link_ref, l.confidence
        FROM catalog_product_commercial_link l
        JOIN catalog_product p ON p.id = l.product_id
        ORDER BY l.link_kind, l.link_ref
        """
    ):
        d = _row_dict(row)
        assert_mirror_text_safe(d.get("link_ref"), field="link_ref")
        assert_mirror_row_safe(d, table="product_commercial_link")
        commercial_links.append(d)

    commercial_history: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT
          h.history_key, p.product_key, h.deal_key, h.deal_label,
          h.client_org_name, h.supplier_org_name, h.line_side, h.line_kind,
          h.quantity, h.unit, h.currency, h.amount_net_clp, h.amount_decimal,
          h.amount_minor, h.unit_price_decimal, h.total_price_decimal,
          h.margin_status, h.deal_status, h.is_public_safe, h.source_summary,
          h.confidence
        FROM catalog_product_commercial_history h
        JOIN catalog_product p ON p.id = h.product_id
        ORDER BY h.deal_key, h.line_side, h.line_kind, h.history_key
        """
    ):
        d = _row_dict(row)
        d["is_public_safe"] = _bool_from_sqlite(d.get("is_public_safe"))
        assert_mirror_row_safe(d, table="product_commercial_history")
        if d["is_public_safe"] and d.get("line_side") == "supplier":
            raise CatalogMirrorSafetyError(
                f"commercial_history {d['history_key']}: supplier rows must not be public_safe"
            )
        commercial_history.append(d)

    return {
        "products": products,
        "categories": categories,
        "aliases": aliases,
        "category_maps": category_maps,
        "specs": specs,
        "supplier_offers": supplier_offers,
        "price_snapshots": price_snapshots,
        "commercial_links": commercial_links,
        "commercial_history": commercial_history,
    }


def sqlite_catalog_counts(conn: sqlite3.Connection) -> dict[str, int]:
    if not catalog_tables_exist(conn):
        return {name: 0 for name in (
            "products",
            "categories",
            "aliases",
            "category_maps",
            "specs",
            "supplier_offers",
            "price_snapshots",
            "commercial_links",
            "commercial_history",
        )}
    mapping = {
        "products": "catalog_product",
        "categories": "catalog_product_category",
        "aliases": "catalog_product_alias",
        "category_maps": "catalog_product_category_map",
        "specs": "catalog_product_spec",
        "supplier_offers": "catalog_supplier_offer",
        "price_snapshots": "catalog_price_snapshot",
        "commercial_links": "catalog_product_commercial_link",
        "commercial_history": "catalog_product_commercial_history",
    }
    return {k: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for k, t in mapping.items()}
