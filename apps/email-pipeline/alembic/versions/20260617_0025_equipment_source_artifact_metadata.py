"""Add source artifact metadata columns to equipment_opportunity_source.

Revision ID: 20260617_0025
Revises: 20260614_0024
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260617_0025"
down_revision: Union[str, Sequence[str], None] = "20260614_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE commercial.equipment_opportunity_source
          ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'csv_artifact',
          ADD COLUMN artifact_basename TEXT,
          ADD COLUMN canonical_reason TEXT
        """
    )
    op.execute(
        """
        UPDATE commercial.equipment_opportunity_source
        SET
          source_kind = 'csv_artifact',
          artifact_basename = NULLIF(regexp_replace(csv_path, '^.+[/\\\\]', ''), ''),
          canonical_reason = CASE
            WHEN is_canonical = TRUE THEN 'existing_canonical_source'
            ELSE NULL
          END
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.equipment_opportunity_source.source_kind IS
          'Kind of source artifact or domain source used for this read-model load.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.equipment_opportunity_source.artifact_basename IS
          'Safe basename of the source artifact; does not contain local filesystem directories.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.equipment_opportunity_source.canonical_reason IS
          'Reason this source was or was not promoted as canonical.'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE commercial.equipment_opportunity_source
          DROP COLUMN IF EXISTS canonical_reason,
          DROP COLUMN IF EXISTS artifact_basename,
          DROP COLUMN IF EXISTS source_kind
        """
    )
