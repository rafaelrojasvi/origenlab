"""Add source_type and Gmail history columns to lead_intel.prospect.

Revision ID: 20260531_0022
Revises: 20260528_0021
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260531_0022"
down_revision: Union[str, Sequence[str], None] = "20260528_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lead_intel.prospect
          ADD COLUMN IF NOT EXISTS source_type TEXT,
          ADD COLUMN IF NOT EXISTS dataset_label TEXT,
          ADD COLUMN IF NOT EXISTS gmail_first_contacted_at TEXT,
          ADD COLUMN IF NOT EXISTS gmail_last_contacted_at TEXT,
          ADD COLUMN IF NOT EXISTS gmail_sent_count INTEGER,
          ADD COLUMN IF NOT EXISTS gmail_received_count INTEGER,
          ADD COLUMN IF NOT EXISTS gmail_latest_subject_safe TEXT
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lead_intel_prospect_source_type "
        "ON lead_intel.prospect (source_type)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS lead_intel.idx_lead_intel_prospect_source_type")
    op.execute(
        """
        ALTER TABLE lead_intel.prospect
          DROP COLUMN IF EXISTS gmail_latest_subject_safe,
          DROP COLUMN IF EXISTS gmail_received_count,
          DROP COLUMN IF EXISTS gmail_sent_count,
          DROP COLUMN IF EXISTS gmail_last_contacted_at,
          DROP COLUMN IF EXISTS gmail_first_contacted_at,
          DROP COLUMN IF EXISTS dataset_label,
          DROP COLUMN IF EXISTS source_type
        """
    )
