"""Mart schema: document_master only (Slice 2B).

Revision ID: 20260419_0003
Revises: 20260419_0002
Create Date: 2026-04-19

DDL only; no data migration. No SQLite runtime changes.
See docs/pipeline/POSTGRES_SCHEMA_TARGET_V1.md and POSTGRES_SCHEMA_RECONCILIATION_V1.md.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260419_0003"
down_revision: Union[str, Sequence[str], None] = "20260419_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mart.document_master (
          attachment_id BIGINT PRIMARY KEY
            REFERENCES archive.attachments(id) ON DELETE CASCADE,
          email_id BIGINT
            REFERENCES archive.emails(id) ON DELETE CASCADE,
          filename TEXT,
          extension TEXT,
          sender_email TEXT,
          sender_domain TEXT,
          recipient_domain TEXT,
          sent_at TIMESTAMPTZ,
          doc_type TEXT,
          has_quote_terms BOOLEAN,
          has_invoice_terms BOOLEAN,
          has_purchase_terms BOOLEAN,
          has_price_list_terms BOOLEAN,
          equipment_tags TEXT,
          extracted_preview_raw TEXT,
          extracted_preview_clean TEXT,
          preview_quality_score DOUBLE PRECISION
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_document_master_sender_domain
          ON mart.document_master(sender_domain)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_document_master_recipient_domain
          ON mart.document_master(recipient_domain)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_document_master_sent_at
          ON mart.document_master(sent_at)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mart_document_master_doc_type
          ON mart.document_master(doc_type)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mart_document_master_doc_type")
    op.execute("DROP INDEX IF EXISTS idx_mart_document_master_sent_at")
    op.execute("DROP INDEX IF EXISTS idx_mart_document_master_recipient_domain")
    op.execute("DROP INDEX IF EXISTS idx_mart_document_master_sender_domain")
    op.execute("DROP TABLE IF EXISTS mart.document_master")
