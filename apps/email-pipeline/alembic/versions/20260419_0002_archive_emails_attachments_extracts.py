"""Archive schema: emails, attachments, attachment_extracts (Slice 2A).

Revision ID: 20260419_0002
Revises: 20260419_0001
Create Date: 2026-04-19

See docs/pipeline/POSTGRES_SCHEMA_TARGET_V1.md and POSTGRES_SCHEMA_RECONCILIATION_V1.md.
Data migration is out of scope; DDL only.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260419_0002"
down_revision: Union[str, Sequence[str], None] = "20260419_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE archive.emails (
          id BIGSERIAL PRIMARY KEY,
          source_file TEXT NOT NULL,
          folder TEXT,
          message_id TEXT,
          subject TEXT,
          sender TEXT,
          recipients TEXT,
          date_raw TEXT,
          date_iso TIMESTAMPTZ,
          body TEXT,
          body_html TEXT,
          body_text_raw TEXT,
          body_text_clean TEXT,
          body_source_type TEXT,
          body_has_plain BOOLEAN,
          body_has_html BOOLEAN,
          full_body_clean TEXT,
          top_reply_clean TEXT,
          attachment_count INTEGER,
          has_attachments BOOLEAN
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_emails_message_id
          ON archive.emails(message_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_emails_date_iso
          ON archive.emails(date_iso)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_emails_body_source_type
          ON archive.emails(body_source_type)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_emails_source_file_folder
          ON archive.emails(source_file, folder)
        """
    )

    op.execute(
        """
        CREATE TABLE archive.attachments (
          id BIGSERIAL PRIMARY KEY,
          email_id BIGINT NOT NULL REFERENCES archive.emails(id) ON DELETE CASCADE,
          part_index INTEGER NOT NULL,
          filename TEXT,
          content_type TEXT,
          content_disposition TEXT,
          size_bytes BIGINT,
          content_id TEXT,
          is_inline BOOLEAN,
          sha256 TEXT,
          saved_path TEXT,
          created_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_attachments_email_id
          ON archive.attachments(email_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_attachments_sha256
          ON archive.attachments(sha256)
        """
    )

    op.execute(
        """
        CREATE TABLE archive.attachment_extracts (
          id BIGSERIAL PRIMARY KEY,
          attachment_id BIGINT NOT NULL REFERENCES archive.attachments(id) ON DELETE CASCADE,
          extract_status TEXT NOT NULL,
          extract_method TEXT NOT NULL,
          text_preview TEXT,
          text_truncated TEXT,
          char_count INTEGER,
          page_count INTEGER,
          sheet_count INTEGER,
          detected_doc_type TEXT,
          has_quote_terms BOOLEAN,
          has_invoice_terms BOOLEAN,
          has_price_list_terms BOOLEAN,
          has_purchase_terms BOOLEAN,
          error_message TEXT,
          created_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX idx_archive_attachment_extracts_attachment_id
          ON archive.attachment_extracts(attachment_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_attachment_extracts_doc_type
          ON archive.attachment_extracts(detected_doc_type)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_archive_attachment_extracts_status_method
          ON archive.attachment_extracts(extract_status, extract_method)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_archive_attachment_extracts_status_method")
    op.execute("DROP INDEX IF EXISTS idx_archive_attachment_extracts_doc_type")
    op.execute("DROP INDEX IF EXISTS idx_archive_attachment_extracts_attachment_id")
    op.execute("DROP TABLE IF EXISTS archive.attachment_extracts")

    op.execute("DROP INDEX IF EXISTS idx_archive_attachments_sha256")
    op.execute("DROP INDEX IF EXISTS idx_archive_attachments_email_id")
    op.execute("DROP TABLE IF EXISTS archive.attachments")

    op.execute("DROP INDEX IF EXISTS idx_archive_emails_source_file_folder")
    op.execute("DROP INDEX IF EXISTS idx_archive_emails_body_source_type")
    op.execute("DROP INDEX IF EXISTS idx_archive_emails_date_iso")
    op.execute("DROP INDEX IF EXISTS idx_archive_emails_message_id")
    op.execute("DROP TABLE IF EXISTS archive.emails")
