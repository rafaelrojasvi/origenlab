"""Outbound durable sidecar tables only (Slice 3A).

Revision ID: 20260419_0004
Revises: 20260419_0003
Create Date: 2026-04-19

DDL only; no data migration. No SQLite runtime changes.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260419_0004"
down_revision: Union[str, Sequence[str], None] = "20260419_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE outbound.contact_email_suppression (
          email TEXT PRIMARY KEY,
          suppression_reason_code TEXT NOT NULL,
          suppression_reason_text TEXT,
          suppression_source TEXT,
          last_bounced_at TIMESTAMPTZ,
          updated_at TIMESTAMPTZ NOT NULL,
          updated_by TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_contact_email_suppression_reason
          ON outbound.contact_email_suppression(suppression_reason_code)
        """
    )

    op.execute(
        """
        CREATE TABLE outbound.contact_domain_suppression (
          domain_norm TEXT PRIMARY KEY,
          suppression_reason_text TEXT,
          updated_at TIMESTAMPTZ NOT NULL,
          updated_by TEXT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE outbound.outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          first_contacted_at TIMESTAMPTZ,
          last_contacted_at TIMESTAMPTZ,
          source TEXT,
          notes TEXT,
          updated_at TIMESTAMPTZ NOT NULL,
          updated_by TEXT,
          lead_id BIGINT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_outreach_contact_state_state
          ON outbound.outreach_contact_state(state)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_outbound_outreach_contact_state_lead_id
          ON outbound.outreach_contact_state(lead_id)
          WHERE lead_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_outbound_outreach_contact_state_lead_id")
    op.execute("DROP INDEX IF EXISTS idx_outbound_outreach_contact_state_state")
    op.execute("DROP TABLE IF EXISTS outbound.outreach_contact_state")

    op.execute("DROP TABLE IF EXISTS outbound.contact_domain_suppression")

    op.execute("DROP INDEX IF EXISTS idx_outbound_contact_email_suppression_reason")
    op.execute("DROP TABLE IF EXISTS outbound.contact_email_suppression")
