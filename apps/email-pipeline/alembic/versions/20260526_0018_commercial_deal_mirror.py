"""Commercial deal ledger read-model mirror (redacted dashboard).

Revision ID: 20260526_0018
Revises: 20260524_0017
Create Date: 2026-05-26

Populated from SQLite commercial_deal* via sync_commercial_deals (opt-in).
No email bodies, transfer IDs, or operator-only paths.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260526_0018"
down_revision: Union[str, Sequence[str], None] = "20260524_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE commercial.deal (
          deal_key TEXT PRIMARY KEY,
          sync_run_id BIGINT,
          client_org_name TEXT NOT NULL,
          supplier_org_name TEXT NOT NULL,
          deal_status TEXT NOT NULL,
          margin_status TEXT NOT NULL,
          reconciliation_status TEXT,
          freight_status TEXT,
          client_sale_net_clp BIGINT,
          client_iva_amount_clp BIGINT,
          client_sale_gross_clp BIGINT,
          client_payment_received_clp BIGINT,
          supplier_invoice_total_decimal TEXT,
          supplier_invoice_total_minor INTEGER,
          supplier_amount_paid_decimal TEXT,
          supplier_amount_paid_minor INTEGER,
          margin_net_clp BIGINT,
          margin_pct DOUBLE PRECISION,
          updated_at TEXT,
          product_line_summaries JSONB NOT NULL DEFAULT '[]'::jsonb,
          cost_summaries_by_type JSONB NOT NULL DEFAULT '[]'::jsonb,
          payment_summaries_masked JSONB NOT NULL DEFAULT '[]'::jsonb,
          margin_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_commercial_deal_updated_at
          ON commercial.deal (updated_at DESC NULLS LAST)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_commercial_deal_margin_status
          ON commercial.deal (margin_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commercial.deal")
