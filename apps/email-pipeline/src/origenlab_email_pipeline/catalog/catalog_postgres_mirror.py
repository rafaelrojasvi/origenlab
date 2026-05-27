"""Mirror SQLite catalog_* tables into Postgres catalog.* (read-only, redacted)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.catalog.catalog_mirror_read_model import (
    load_catalog_mirror_payload,
    sqlite_catalog_counts,
)
from origenlab_email_pipeline.catalog.catalog_schema import catalog_tables_exist
from origenlab_email_pipeline.mart_core_postgres_migrate import connect_sqlite_readonly

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

CATALOG_PG_TABLES: tuple[tuple[str, str], ...] = (
    ("catalog", "product"),
    ("catalog", "product_category"),
    ("catalog", "product_alias"),
    ("catalog", "product_category_map"),
    ("catalog", "product_spec"),
    ("catalog", "supplier_offer"),
    ("catalog", "price_snapshot"),
    ("catalog", "product_commercial_link"),
    ("catalog", "product_commercial_history"),
)

# Delete order: children first.
_CATALOG_DELETE_ORDER: tuple[tuple[str, str], ...] = tuple(reversed(CATALOG_PG_TABLES))


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            f"psycopg is required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


def pg_catalog_tables_exist(cur: Any) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'catalog' AND table_name = 'product'
        LIMIT 1
        """
    )
    return cur.fetchone() is not None


def sync_catalog_postgres_mirror(
    pg_url: str,
    sqlite_path: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Full replace catalog.* from SQLite catalog_* (redacted read model)."""
    _require_psycopg()
    assert psycopg is not None

    conn = connect_sqlite_readonly(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        payload = load_catalog_mirror_payload(conn)
        sqlite_counts = sqlite_catalog_counts(conn)
    finally:
        conn.close()

    built_counts = {k: len(payload[k]) for k in payload}
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "skipped": False,
        "sqlite_counts": sqlite_counts,
        "built_counts": built_counts,
        "written_counts": {k: 0 for k in built_counts},
    }

    if dry_run:
        result["skipped"] = True
        return result

    synced_at = datetime.now(timezone.utc)

    with psycopg.connect(pg_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:
            if not pg_catalog_tables_exist(cur):
                result["skipped"] = True
                result["reason"] = "table_missing"
                return result

            for schema, table in _CATALOG_DELETE_ORDER:
                cur.execute(f"DELETE FROM {schema}.{table}")

            for row in payload["products"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product (
                      product_key, display_name, brand, manufacturer_name, product_kind,
                      equipment_class, model_number, default_unit, website_slug,
                      website_product_id, public_summary, is_active, confidence, synced_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        row["product_key"],
                        row["display_name"],
                        row.get("brand"),
                        row.get("manufacturer_name"),
                        row["product_kind"],
                        row.get("equipment_class"),
                        row.get("model_number"),
                        row.get("default_unit"),
                        row.get("website_slug"),
                        row.get("website_product_id"),
                        row.get("public_summary"),
                        row["is_active"],
                        row["confidence"],
                        synced_at,
                    ),
                )
            result["written_counts"]["products"] = len(payload["products"])

            for row in payload["categories"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product_category (
                      category_key, parent_category_key, display_name, equipment_class, synced_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        row["category_key"],
                        row.get("parent_category_key"),
                        row["display_name"],
                        row.get("equipment_class"),
                        synced_at,
                    ),
                )
            result["written_counts"]["categories"] = len(payload["categories"])

            for row in payload["aliases"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product_alias (
                      alias_source, alias_code, product_key, alias_kind, synced_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        row["alias_source"],
                        row["alias_code"],
                        row["product_key"],
                        row.get("alias_kind"),
                        synced_at,
                    ),
                )
            result["written_counts"]["aliases"] = len(payload["aliases"])

            for row in payload["category_maps"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product_category_map (
                      product_key, category_key, is_primary, synced_at
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        row["product_key"],
                        row["category_key"],
                        row["is_primary"],
                        synced_at,
                    ),
                )
            result["written_counts"]["category_maps"] = len(payload["category_maps"])

            for row in payload["specs"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product_spec (
                      product_key, spec_group, spec_key, spec_value, spec_value_numeric,
                      spec_unit, source, confidence, synced_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["product_key"],
                        row.get("spec_group"),
                        row["spec_key"],
                        row["spec_value"],
                        row.get("spec_value_numeric"),
                        row.get("spec_unit"),
                        row["source"],
                        row["confidence"],
                        synced_at,
                    ),
                )
            result["written_counts"]["specs"] = len(payload["specs"])

            for row in payload["supplier_offers"]:
                cur.execute(
                    """
                    INSERT INTO catalog.supplier_offer (
                      offer_key, product_key, supplier_org_name, supplier_domain,
                      offer_status, quoted_at, valid_until, incoterm, payment_terms,
                      delivery_terms, currency, quantity_offered, availability_note,
                      confidence, synced_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        row["offer_key"],
                        row["product_key"],
                        row.get("supplier_org_name"),
                        row.get("supplier_domain"),
                        row["offer_status"],
                        row.get("quoted_at"),
                        row.get("valid_until"),
                        row.get("incoterm"),
                        row.get("payment_terms"),
                        row.get("delivery_terms"),
                        row.get("currency"),
                        row.get("quantity_offered"),
                        row.get("availability_note"),
                        row["confidence"],
                        synced_at,
                    ),
                )
            result["written_counts"]["supplier_offers"] = len(payload["supplier_offers"])

            for row in payload["price_snapshots"]:
                cur.execute(
                    """
                    INSERT INTO catalog.price_snapshot (
                      snapshot_key, product_key, offer_key, snapshot_kind,
                      currency, amount_decimal, amount_minor, amount_clp_integer,
                      quantity, unit, incoterm, price_notes, is_public_safe,
                      confidence, observed_at, synced_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        row["snapshot_key"],
                        row["product_key"],
                        row.get("offer_key"),
                        row["snapshot_kind"],
                        row.get("currency"),
                        row.get("amount_decimal"),
                        row.get("amount_minor"),
                        row.get("amount_clp_integer"),
                        row.get("quantity"),
                        row.get("unit"),
                        row.get("incoterm"),
                        row.get("price_notes"),
                        False,
                        row["confidence"],
                        row.get("observed_at"),
                        synced_at,
                    ),
                )
            result["written_counts"]["price_snapshots"] = len(payload["price_snapshots"])

            for row in payload["commercial_links"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product_commercial_link (
                      link_kind, link_ref, product_key, confidence, synced_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        row["link_kind"],
                        row["link_ref"],
                        row["product_key"],
                        row["confidence"],
                        synced_at,
                    ),
                )
            result["written_counts"]["commercial_links"] = len(payload["commercial_links"])

            for row in payload["commercial_history"]:
                cur.execute(
                    """
                    INSERT INTO catalog.product_commercial_history (
                      history_key, product_key, deal_key, deal_label,
                      client_org_name, supplier_org_name, line_side, line_kind,
                      quantity, unit, currency, amount_net_clp, amount_decimal,
                      amount_minor, unit_price_decimal, total_price_decimal,
                      margin_status, deal_status, is_public_safe, source_summary,
                      confidence, synced_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        row["history_key"],
                        row["product_key"],
                        row["deal_key"],
                        row["deal_label"],
                        row.get("client_org_name"),
                        row.get("supplier_org_name"),
                        row["line_side"],
                        row["line_kind"],
                        row.get("quantity"),
                        row.get("unit"),
                        row.get("currency"),
                        row.get("amount_net_clp"),
                        row.get("amount_decimal"),
                        row.get("amount_minor"),
                        row.get("unit_price_decimal"),
                        row.get("total_price_decimal"),
                        row.get("margin_status"),
                        row.get("deal_status"),
                        False,
                        row.get("source_summary"),
                        row["confidence"],
                        synced_at,
                    ),
                )
            result["written_counts"]["commercial_history"] = len(payload["commercial_history"])

        pg_conn.commit()

    return result


def postgres_catalog_counts(pg_url: str) -> dict[str, int]:
    """Read row counts from Postgres catalog.* mirror tables."""
    _require_psycopg()
    assert psycopg is not None

    pg_mapping = {
        "products": ("catalog", "product"),
        "categories": ("catalog", "product_category"),
        "aliases": ("catalog", "product_alias"),
        "category_maps": ("catalog", "product_category_map"),
        "specs": ("catalog", "product_spec"),
        "supplier_offers": ("catalog", "supplier_offer"),
        "price_snapshots": ("catalog", "price_snapshot"),
        "commercial_links": ("catalog", "product_commercial_link"),
        "commercial_history": ("catalog", "product_commercial_history"),
    }
    out: dict[str, int] = {}
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            if not pg_catalog_tables_exist(cur):
                return {k: 0 for k in pg_mapping}
            for key, (schema, table) in pg_mapping.items():
                cur.execute(f"SELECT COUNT(*)::bigint FROM {schema}.{table}")
                out[key] = int(cur.fetchone()[0])
    return out
