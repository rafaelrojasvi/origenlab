"""Catalog product commercial history mirror (Phase 8F).

Revision ID: 20260528_0020
Revises: 20260527_0019
Create Date: 2026-05-28

Redacted per-product deal line summaries for dashboard catalog detail.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260528_0020"
down_revision: Union[str, Sequence[str], None] = "20260527_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE catalog.product_commercial_history (
          history_key TEXT PRIMARY KEY,
          product_key TEXT NOT NULL REFERENCES catalog.product(product_key) ON DELETE CASCADE,
          deal_key TEXT NOT NULL,
          deal_label TEXT NOT NULL,
          client_org_name TEXT,
          supplier_org_name TEXT,
          line_side TEXT NOT NULL,
          line_kind TEXT NOT NULL,
          quantity TEXT,
          unit TEXT,
          currency TEXT,
          amount_net_clp BIGINT,
          amount_decimal TEXT,
          amount_minor BIGINT,
          unit_price_decimal TEXT,
          total_price_decimal TEXT,
          margin_status TEXT,
          deal_status TEXT,
          is_public_safe BOOLEAN NOT NULL DEFAULT FALSE,
          source_summary TEXT,
          confidence TEXT NOT NULL,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_commercial_history_product
          ON catalog.product_commercial_history (product_key)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_catalog_commercial_history_deal
          ON catalog.product_commercial_history (deal_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog.product_commercial_history")
