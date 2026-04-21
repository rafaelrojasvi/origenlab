"""Outbound export audit tables only (Slice 3B).

Revision ID: 20260419_0005
Revises: 20260419_0004
Create Date: 2026-04-19

DDL only; no data migration. No SQLite runtime changes.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260419_0005"
down_revision: Union[str, Sequence[str], None] = "20260419_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE outbound.outbound_batch (
          id BIGSERIAL PRIMARY KEY,
          lane TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by TEXT,
          gmail_user TEXT NOT NULL,
          sent_folders TEXT[] NOT NULL,
          sent_preflight_json JSONB NOT NULL,
          gate_version TEXT,
          output_artifact_path TEXT,
          notes TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_lane_created_at
          ON outbound.outbound_batch(lane, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_created_at
          ON outbound.outbound_batch(created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE outbound.outbound_batch_recipient (
          id BIGSERIAL PRIMARY KEY,
          batch_id BIGINT NOT NULL REFERENCES outbound.outbound_batch(id) ON DELETE CASCADE,
          email_norm TEXT NOT NULL,
          lead_id BIGINT,
          source_kind TEXT,
          source_key TEXT,
          organization_name TEXT,
          organization_domain TEXT,
          eligibility_result TEXT NOT NULL,
          exclusion_reason TEXT,
          exported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_outbound_batch_recipient_batch_email
          ON outbound.outbound_batch_recipient(batch_id, email_norm)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_recipient_batch_id
          ON outbound.outbound_batch_recipient(batch_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_recipient_email_norm
          ON outbound.outbound_batch_recipient(email_norm)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_recipient_lead_id
          ON outbound.outbound_batch_recipient(lead_id)
          WHERE lead_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_recipient_eligibility_result
          ON outbound.outbound_batch_recipient(eligibility_result)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_batch_recipient_exclusion_reason
          ON outbound.outbound_batch_recipient(exclusion_reason)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_recipient_exclusion_reason")
    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_recipient_eligibility_result")
    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_recipient_lead_id")
    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_recipient_email_norm")
    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_recipient_batch_id")
    op.execute("DROP INDEX IF EXISTS uq_outbound_batch_recipient_batch_email")
    op.execute("DROP TABLE IF EXISTS outbound.outbound_batch_recipient")

    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_created_at")
    op.execute("DROP INDEX IF EXISTS idx_outbound_batch_lane_created_at")
    op.execute("DROP TABLE IF EXISTS outbound.outbound_batch")
