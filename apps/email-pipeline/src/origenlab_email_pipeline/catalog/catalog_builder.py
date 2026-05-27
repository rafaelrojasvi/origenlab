"""Build / upsert catalog tables from validated seed (Phase 8B)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.catalog.catalog_schema import ensure_catalog_tables
from origenlab_email_pipeline.catalog.catalog_seed import (
    CatalogSeedValidationError,
    load_seed_json,
    normalize_alias_code,
    validate_seed,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import decimal_to_minor
from origenlab_email_pipeline.timeutil import now_iso


@dataclass
class CatalogBuildSummary:
    dry_run: bool
    products: int = 0
    aliases: int = 0
    categories: int = 0
    category_maps: int = 0
    specs: int = 0
    supplier_offers: int = 0
    price_snapshots: int = 0
    commercial_links: int = 0
    commercial_history: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "products": self.products,
            "aliases": self.aliases,
            "categories": self.categories,
            "category_maps": self.category_maps,
            "specs": self.specs,
            "supplier_offers": self.supplier_offers,
            "price_snapshots": self.price_snapshots,
            "commercial_links": self.commercial_links,
            "commercial_history": self.commercial_history,
        }


def build_catalog_from_seed(
    conn: sqlite3.Connection,
    seed: dict[str, Any],
    *,
    dry_run: bool = False,
) -> CatalogBuildSummary:
    validate_seed(seed)
    summary = CatalogBuildSummary(dry_run=dry_run)

    if dry_run:
        summary.categories = len(seed.get("categories") or [])
        for prod in seed.get("products") or []:
            summary.products += 1
            summary.aliases += len(prod.get("aliases") or [])
            summary.category_maps += len(prod.get("category_keys") or [])
            summary.specs += len(prod.get("specs") or [])
            summary.supplier_offers += len(prod.get("supplier_offers") or [])
            summary.price_snapshots += len(prod.get("price_snapshots") or [])
            summary.commercial_links += len(prod.get("commercial_links") or [])
            summary.commercial_history += len(prod.get("commercial_history") or [])
        return summary

    ensure_catalog_tables(conn)
    ts = now_iso()
    category_id_by_key: dict[str, int] = {}

    for cat in seed.get("categories") or []:
        ck = str(cat["category_key"])
        conn.execute(
            """
            INSERT INTO catalog_product_category (
              category_key, parent_category_key, display_name, equipment_class,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(category_key) DO UPDATE SET
              parent_category_key = excluded.parent_category_key,
              display_name = excluded.display_name,
              equipment_class = excluded.equipment_class,
              updated_at = excluded.updated_at
            """,
            (
                ck,
                cat.get("parent_category_key"),
                str(cat["display_name"]),
                cat.get("equipment_class"),
                ts,
                ts,
            ),
        )
        row = conn.execute(
            "SELECT id FROM catalog_product_category WHERE category_key = ?",
            (ck,),
        ).fetchone()
        assert row is not None
        category_id_by_key[ck] = int(row[0])
        summary.categories += 1

    product_id_by_key: dict[str, int] = {}

    for prod in seed.get("products") or []:
        pk = str(prod["product_key"])
        conn.execute(
            """
            INSERT INTO catalog_product (
              product_key, display_name, brand, manufacturer_name, product_kind,
              equipment_class, model_number, default_unit, website_slug, website_product_id,
              public_summary, is_active, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(product_key) DO UPDATE SET
              display_name = excluded.display_name,
              brand = excluded.brand,
              manufacturer_name = excluded.manufacturer_name,
              product_kind = excluded.product_kind,
              equipment_class = excluded.equipment_class,
              model_number = excluded.model_number,
              default_unit = excluded.default_unit,
              website_slug = excluded.website_slug,
              website_product_id = excluded.website_product_id,
              public_summary = excluded.public_summary,
              confidence = excluded.confidence,
              updated_at = excluded.updated_at
            """,
            (
                pk,
                str(prod["display_name"]),
                prod.get("brand"),
                prod.get("manufacturer_name"),
                str(prod["product_kind"]),
                prod.get("equipment_class"),
                prod.get("model_number"),
                prod.get("default_unit"),
                prod.get("website_slug"),
                prod.get("website_product_id"),
                str(prod["public_summary"]),
                str(prod["confidence"]),
                ts,
                ts,
            ),
        )
        row = conn.execute(
            "SELECT id FROM catalog_product WHERE product_key = ?",
            (pk,),
        ).fetchone()
        assert row is not None
        product_id = int(row[0])
        product_id_by_key[pk] = product_id
        summary.products += 1

        conn.execute("DELETE FROM catalog_product_alias WHERE product_id = ?", (product_id,))
        for alias in prod.get("aliases") or []:
            norm = normalize_alias_code(str(alias["alias_code"]))
            conn.execute(
                """
                INSERT INTO catalog_product_alias (
                  product_id, alias_code, alias_source, alias_kind, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    norm,
                    str(alias["alias_source"]),
                    alias.get("alias_kind"),
                    alias.get("notes"),
                    ts,
                ),
            )
            summary.aliases += 1

        conn.execute("DELETE FROM catalog_product_category_map WHERE product_id = ?", (product_id,))
        primary_set = False
        for ck in prod.get("category_keys") or []:
            is_primary = 0 if primary_set else 1
            primary_set = True
            conn.execute(
                """
                INSERT INTO catalog_product_category_map (
                  product_id, category_id, is_primary, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (product_id, category_id_by_key[str(ck)], is_primary, ts),
            )
            summary.category_maps += 1

        conn.execute("DELETE FROM catalog_product_spec WHERE product_id = ?", (product_id,))
        for spec in prod.get("specs") or []:
            conn.execute(
                """
                INSERT INTO catalog_product_spec (
                  product_id, spec_group, spec_key, spec_value, spec_value_numeric,
                  spec_unit, source, confidence, valid_from, valid_to, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    spec.get("spec_group"),
                    str(spec["spec_key"]),
                    str(spec["spec_value"]),
                    spec.get("spec_value_numeric"),
                    spec.get("spec_unit"),
                    str(spec.get("source", "operator")),
                    str(spec.get("confidence", prod["confidence"])),
                    spec.get("valid_from"),
                    spec.get("valid_to"),
                    ts,
                ),
            )
            summary.specs += 1

        offer_id_by_key: dict[str, int] = {}
        for offer in prod.get("supplier_offers") or []:
            ok = str(offer["offer_key"])
            conn.execute(
                """
                INSERT INTO catalog_supplier_offer (
                  offer_key, product_id, supplier_org_name, supplier_domain, offer_status,
                  quoted_at, valid_until, incoterm, payment_terms, delivery_terms,
                  currency, quantity_offered, availability_note,
                  evidence_email_id, evidence_attachment_id, confidence,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(offer_key) DO UPDATE SET
                  product_id = excluded.product_id,
                  supplier_org_name = excluded.supplier_org_name,
                  supplier_domain = excluded.supplier_domain,
                  offer_status = excluded.offer_status,
                  quoted_at = excluded.quoted_at,
                  valid_until = excluded.valid_until,
                  incoterm = excluded.incoterm,
                  payment_terms = excluded.payment_terms,
                  delivery_terms = excluded.delivery_terms,
                  currency = excluded.currency,
                  quantity_offered = excluded.quantity_offered,
                  availability_note = excluded.availability_note,
                  confidence = excluded.confidence,
                  updated_at = excluded.updated_at
                """,
                (
                    ok,
                    product_id,
                    offer.get("supplier_org_name"),
                    offer.get("supplier_domain"),
                    str(offer.get("offer_status", "received")),
                    offer.get("quoted_at"),
                    offer.get("valid_until"),
                    offer.get("incoterm"),
                    offer.get("payment_terms"),
                    offer.get("delivery_terms"),
                    offer.get("currency"),
                    offer.get("quantity_offered"),
                    offer.get("availability_note"),
                    offer.get("evidence_email_id"),
                    offer.get("evidence_attachment_id"),
                    str(offer.get("confidence", prod["confidence"])),
                    ts,
                    ts,
                ),
            )
            row = conn.execute(
                "SELECT id FROM catalog_supplier_offer WHERE offer_key = ?",
                (ok,),
            ).fetchone()
            assert row is not None
            offer_id_by_key[ok] = int(row[0])
            summary.supplier_offers += 1

        for snap in prod.get("price_snapshots") or []:
            sk = str(snap["snapshot_key"])
            offer_id = None
            offer_key = snap.get("supplier_offer_key")
            if offer_key:
                offer_id = offer_id_by_key.get(str(offer_key))
            currency = snap.get("currency")
            amount_decimal = snap.get("amount_decimal")
            amount_minor = snap.get("amount_minor")
            if amount_decimal is not None and currency and amount_minor is None:
                amount_minor = decimal_to_minor(str(amount_decimal), str(currency))
            conn.execute(
                """
                INSERT INTO catalog_price_snapshot (
                  snapshot_key, product_id, supplier_offer_id, snapshot_kind,
                  currency, amount_decimal, amount_minor, amount_clp_integer,
                  quantity, unit, incoterm, price_notes, is_public_safe,
                  confidence, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(snapshot_key) DO UPDATE SET
                  product_id = excluded.product_id,
                  supplier_offer_id = excluded.supplier_offer_id,
                  snapshot_kind = excluded.snapshot_kind,
                  currency = excluded.currency,
                  amount_decimal = excluded.amount_decimal,
                  amount_minor = excluded.amount_minor,
                  amount_clp_integer = excluded.amount_clp_integer,
                  quantity = excluded.quantity,
                  unit = excluded.unit,
                  incoterm = excluded.incoterm,
                  price_notes = excluded.price_notes,
                  is_public_safe = 0,
                  confidence = excluded.confidence,
                  observed_at = excluded.observed_at
                """,
                (
                    sk,
                    product_id,
                    offer_id,
                    str(snap.get("snapshot_kind", "supplier_quote")),
                    currency,
                    amount_decimal,
                    amount_minor,
                    snap.get("amount_clp_integer"),
                    snap.get("quantity"),
                    snap.get("unit"),
                    snap.get("incoterm"),
                    snap.get("price_notes"),
                    str(snap.get("confidence", prod["confidence"])),
                    snap.get("observed_at"),
                    ts,
                ),
            )
            summary.price_snapshots += 1

        conn.execute(
            "DELETE FROM catalog_product_commercial_link WHERE product_id = ?",
            (product_id,),
        )
        for link in prod.get("commercial_links") or []:
            conn.execute(
                """
                INSERT INTO catalog_product_commercial_link (
                  product_id, link_kind, link_ref, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(link_kind, link_ref) DO UPDATE SET
                  product_id = excluded.product_id,
                  confidence = excluded.confidence
                """,
                (
                    product_id,
                    str(link["link_kind"]),
                    str(link["link_ref"]),
                    str(link.get("confidence", prod["confidence"])),
                    ts,
                ),
            )
            summary.commercial_links += 1

        conn.execute(
            "DELETE FROM catalog_product_commercial_history WHERE product_id = ?",
            (product_id,),
        )
        for hist in prod.get("commercial_history") or []:
            conn.execute(
                """
                INSERT INTO catalog_product_commercial_history (
                  history_key, product_id, deal_key, deal_label,
                  client_org_name, supplier_org_name, line_side, line_kind,
                  quantity, unit, currency, amount_net_clp, amount_decimal, amount_minor,
                  unit_price_decimal, total_price_decimal, margin_status, deal_status,
                  is_public_safe, source_summary, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(history_key) DO UPDATE SET
                  product_id = excluded.product_id,
                  deal_key = excluded.deal_key,
                  deal_label = excluded.deal_label,
                  client_org_name = excluded.client_org_name,
                  supplier_org_name = excluded.supplier_org_name,
                  line_side = excluded.line_side,
                  line_kind = excluded.line_kind,
                  quantity = excluded.quantity,
                  unit = excluded.unit,
                  currency = excluded.currency,
                  amount_net_clp = excluded.amount_net_clp,
                  amount_decimal = excluded.amount_decimal,
                  amount_minor = excluded.amount_minor,
                  unit_price_decimal = excluded.unit_price_decimal,
                  total_price_decimal = excluded.total_price_decimal,
                  margin_status = excluded.margin_status,
                  deal_status = excluded.deal_status,
                  is_public_safe = excluded.is_public_safe,
                  source_summary = excluded.source_summary,
                  confidence = excluded.confidence
                """,
                (
                    str(hist["history_key"]),
                    product_id,
                    str(hist["deal_key"]),
                    str(hist["deal_label"]),
                    hist.get("client_org_name"),
                    hist.get("supplier_org_name"),
                    str(hist["line_side"]),
                    str(hist["line_kind"]),
                    hist.get("quantity"),
                    hist.get("unit"),
                    hist.get("currency"),
                    hist.get("amount_net_clp"),
                    hist.get("amount_decimal"),
                    hist.get("amount_minor"),
                    hist.get("unit_price_decimal"),
                    hist.get("total_price_decimal"),
                    hist.get("margin_status"),
                    hist.get("deal_status"),
                    0 if not hist.get("is_public_safe") else 1,
                    hist.get("source_summary"),
                    str(hist.get("confidence", prod["confidence"])),
                    ts,
                ),
            )
            summary.commercial_history += 1

    conn.commit()
    _assert_no_orphan_links(conn)
    return summary


def _assert_no_orphan_links(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM catalog_product_commercial_link l
        LEFT JOIN catalog_product p ON p.id = l.product_id
        WHERE p.id IS NULL
        """
    ).fetchone()
    if row and int(row[0]) > 0:
        raise CatalogSeedValidationError("orphan commercial links detected")


def build_catalog_from_seed_file(
    conn: sqlite3.Connection,
    seed_path: Path,
    *,
    dry_run: bool = False,
) -> CatalogBuildSummary:
    seed = load_seed_json(seed_path)
    return build_catalog_from_seed(conn, seed, dry_run=dry_run)
