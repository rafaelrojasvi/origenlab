"""Product catalogue read-model mirror (redacted dashboard).

Revision ID: 20260527_0019
Revises: 20260526_0018
Create Date: 2026-05-27

Populated from SQLite catalog_* via sync_catalog_postgres_mirror (opt-in).
No email evidence IDs, bodies, bank details, or operator-only paths.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260527_0019"
down_revision: Union[str, Sequence[str], None] = "20260526_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS catalog")
    op.execute(
        """
        COMMENT ON SCHEMA catalog IS
          'Redacted product catalogue read model for operator API/dashboard.'
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.product (
          product_key TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          brand TEXT,
          manufacturer_name TEXT,
          product_kind TEXT NOT NULL,
          equipment_class TEXT,
          model_number TEXT,
          default_unit TEXT,
          website_slug TEXT,
          website_product_id TEXT,
          public_summary TEXT,
          is_active BOOLEAN NOT NULL DEFAULT TRUE,
          confidence TEXT NOT NULL,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_product_brand ON catalog.product (brand)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_product_equipment_class
          ON catalog.product (equipment_class)
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.product_category (
          category_key TEXT PRIMARY KEY,
          parent_category_key TEXT,
          display_name TEXT NOT NULL,
          equipment_class TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.product_alias (
          alias_source TEXT NOT NULL,
          alias_code TEXT NOT NULL,
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          alias_kind TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (alias_source, alias_code)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_product_alias_product
          ON catalog.product_alias (product_key)
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.product_category_map (
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          category_key TEXT NOT NULL REFERENCES catalog.product_category(category_key) ON DELETE CASCADE,
          is_primary BOOLEAN NOT NULL DEFAULT FALSE,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (product_key, category_key)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.product_spec (
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          spec_group TEXT,
          spec_key TEXT NOT NULL,
          spec_value TEXT NOT NULL,
          spec_value_numeric DOUBLE PRECISION,
          spec_unit TEXT,
          source TEXT NOT NULL,
          confidence TEXT NOT NULL,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (product_key, spec_key, source)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.supplier_offer (
          offer_key TEXT PRIMARY KEY,
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          supplier_org_name TEXT,
          supplier_domain TEXT,
          offer_status TEXT NOT NULL,
          quoted_at TEXT,
          valid_until TEXT,
          incoterm TEXT,
          payment_terms TEXT,
          delivery_terms TEXT,
          currency TEXT,
          quantity_offered TEXT,
          availability_note TEXT,
          confidence TEXT NOT NULL,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.price_snapshot (
          snapshot_key TEXT PRIMARY KEY,
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          offer_key TEXT REFERENCES catalog.supplier_offer(offer_key) ON DELETE SET NULL,
          snapshot_kind TEXT NOT NULL,
          currency TEXT,
          amount_decimal TEXT,
          amount_minor INTEGER,
          amount_clp_integer BIGINT,
          quantity TEXT,
          unit TEXT,
          incoterm TEXT,
          price_notes TEXT,
          is_public_safe BOOLEAN NOT NULL DEFAULT FALSE,
          confidence TEXT NOT NULL,
          observed_at TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_price_snapshot_product
          ON catalog.price_snapshot (product_key)
        """
    )

    op.execute(
        """
        CREATE TABLE catalog.product_commercial_link (
          link_kind TEXT NOT NULL,
          link_ref TEXT NOT NULL,
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          confidence TEXT NOT NULL,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (link_kind, link_ref)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_commercial_link_product
          ON catalog.product_commercial_link (product_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog.product_commercial_link")
    op.execute("DROP TABLE IF EXISTS catalog.price_snapshot")
    op.execute("DROP TABLE IF EXISTS catalog.supplier_offer")
    op.execute("DROP TABLE IF EXISTS catalog.product_spec")
    op.execute("DROP TABLE IF EXISTS catalog.product_category_map")
    op.execute("DROP TABLE IF EXISTS catalog.product_alias")
    op.execute("DROP TABLE IF EXISTS catalog.product_category")
    op.execute("DROP TABLE IF EXISTS catalog.product")
    op.execute("DROP SCHEMA IF EXISTS catalog")
