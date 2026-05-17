"""Commercial purchase events mirror for dashboard API.

Revision ID: 20260519_0010
Revises: 20260518_0009
Create Date: 2026-05-19

Populated from SQLite commercial_purchase_* tables during dashboard_postgres_sync.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0010"
down_revision: Union[str, Sequence[str], None] = "20260518_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE commercial.purchase_event (
          id BIGINT PRIMARY KEY,
          sync_run_id BIGINT,
          source_email_id BIGINT,
          source_message_id TEXT,
          source_file TEXT,
          email_subject TEXT,
          email_from TEXT,
          email_to TEXT,
          email_date_iso TEXT,
          buyer_org_name TEXT NOT NULL,
          buyer_rut TEXT,
          buyer_contact_name TEXT,
          buyer_contact_role TEXT,
          buyer_contact_email TEXT,
          buyer_domain TEXT,
          purchase_status TEXT NOT NULL,
          oc_number TEXT NOT NULL,
          oc_date TEXT,
          quote_number TEXT,
          quote_date TEXT,
          project_name TEXT,
          project_code TEXT,
          project_responsible TEXT,
          associated_line TEXT,
          net_amount_clp BIGINT,
          iva_amount_clp BIGINT,
          gross_amount_clp BIGINT,
          currency TEXT NOT NULL DEFAULT 'CLP',
          payment_terms TEXT,
          delivery_address TEXT,
          invoice_email TEXT,
          invoice_cc_email TEXT,
          dispatch_requested BOOLEAN NOT NULL DEFAULT FALSE,
          invoice_requested BOOLEAN NOT NULL DEFAULT FALSE,
          bank_details_requested BOOLEAN NOT NULL DEFAULT FALSE,
          commercial_summary TEXT,
          confidence TEXT NOT NULL,
          evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TEXT,
          updated_at TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_commercial_purchase_event_oc_number
          ON commercial.purchase_event (oc_number)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_commercial_purchase_event_email_date
          ON commercial.purchase_event (email_date_iso DESC NULLS LAST)
        """
    )
    op.execute(
        """
        CREATE TABLE commercial.purchase_event_item (
          id BIGINT PRIMARY KEY,
          purchase_event_id BIGINT NOT NULL REFERENCES commercial.purchase_event(id) ON DELETE CASCADE,
          line_number INTEGER NOT NULL,
          ref_code TEXT,
          product_name TEXT NOT NULL,
          brand TEXT,
          quantity TEXT,
          net_amount_clp BIGINT,
          evidence_source TEXT,
          created_at TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_commercial_purchase_event_item_event
          ON commercial.purchase_event_item (purchase_event_id)
        """
    )
    op.execute(
        """
        CREATE TABLE commercial.purchase_event_attachment (
          id BIGINT PRIMARY KEY,
          purchase_event_id BIGINT NOT NULL REFERENCES commercial.purchase_event(id) ON DELETE CASCADE,
          source_attachment_id BIGINT,
          filename TEXT NOT NULL,
          mime_type TEXT,
          document_type TEXT,
          extracted_text_present BOOLEAN NOT NULL DEFAULT FALSE,
          extracted_amounts_json JSONB,
          created_at TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_commercial_purchase_event_attachment_event
          ON commercial.purchase_event_attachment (purchase_event_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commercial.purchase_event_attachment")
    op.execute("DROP TABLE IF EXISTS commercial.purchase_event_item")
    op.execute("DROP TABLE IF EXISTS commercial.purchase_event")
