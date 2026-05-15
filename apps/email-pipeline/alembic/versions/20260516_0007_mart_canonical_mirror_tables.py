"""Canonical Gmail mart mirrors (operational scope for dashboard API).

Revision ID: 20260516_0007
Revises: 20260515_0006
Create Date: 2026-05-16

Populated by scripts/migrate/sqlite_mart_core_to_postgres.py (canonical SELECTs).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260516_0007"
down_revision: Union[str, Sequence[str], None] = "20260515_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mart.contact_master_canonical (
          email TEXT PRIMARY KEY,
          contact_name_best TEXT,
          domain TEXT,
          organization_name_guess TEXT,
          organization_type_guess TEXT,
          first_seen_at TIMESTAMPTZ,
          last_seen_at TIMESTAMPTZ,
          total_emails INTEGER,
          inbound_emails INTEGER,
          outbound_emails INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          business_doc_email_count INTEGER,
          quote_doc_count INTEGER,
          invoice_doc_count INTEGER,
          top_equipment_tags TEXT,
          confidence_score DOUBLE PRECISION
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_contact_master_canonical_domain
          ON mart.contact_master_canonical(domain)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_contact_master_canonical_last_seen
          ON mart.contact_master_canonical(last_seen_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE mart.organization_master_canonical (
          domain TEXT PRIMARY KEY,
          organization_name_guess TEXT,
          organization_type_guess TEXT,
          first_seen_at TIMESTAMPTZ,
          last_seen_at TIMESTAMPTZ,
          total_emails INTEGER,
          total_contacts INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          business_doc_email_count INTEGER,
          quote_doc_count INTEGER,
          invoice_doc_count INTEGER,
          top_equipment_tags TEXT,
          key_contacts TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_organization_master_canonical_last_seen
          ON mart.organization_master_canonical(last_seen_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE mart.opportunity_signals_canonical (
          id BIGSERIAL PRIMARY KEY,
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          email_id BIGINT,
          attachment_id BIGINT,
          score DOUBLE PRECISION,
          details_json JSONB,
          created_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_opportunity_signals_canonical_entity
          ON mart.opportunity_signals_canonical(entity_kind, entity_key)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_opportunity_signals_canonical_type
          ON mart.opportunity_signals_canonical(signal_type)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mart_opportunity_signals_canonical_type")
    op.execute("DROP INDEX IF EXISTS idx_mart_opportunity_signals_canonical_entity")
    op.execute("DROP TABLE IF EXISTS mart.opportunity_signals_canonical")

    op.execute("DROP INDEX IF EXISTS idx_mart_organization_master_canonical_last_seen")
    op.execute("DROP TABLE IF EXISTS mart.organization_master_canonical")

    op.execute("DROP INDEX IF EXISTS idx_mart_contact_master_canonical_last_seen")
    op.execute("DROP INDEX IF EXISTS idx_mart_contact_master_canonical_domain")
    op.execute("DROP TABLE IF EXISTS mart.contact_master_canonical")
