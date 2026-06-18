"""Add stable opportunity_key to commercial.equipment_opportunity.

Revision ID: 20260617_0027
Revises: 20260617_0026
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260617_0027"
down_revision: Union[str, Sequence[str], None] = "20260617_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE commercial.equipment_opportunity
          ADD COLUMN opportunity_key TEXT
        """
    )
    op.execute(
        """
        UPDATE commercial.equipment_opportunity eo
        SET opportunity_key =
          'equipment:' ||
          COALESCE(
            NULLIF(
              regexp_replace(
                regexp_replace(
                  lower(trim(COALESCE(eo.extra_json ->> 'source', ''))),
                  '[^a-z0-9_:-]+', '_', 'g'
                ),
                '(^_+)|(_+$)', '', 'g'
              ),
              ''
            ),
            'equipment_queue'
          ) ||
          ':' ||
          lower(trim(eo.codigo_licitacion))
        """
    )
    op.execute(
        """
        ALTER TABLE commercial.equipment_opportunity
          ALTER COLUMN opportunity_key SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_key
          ON commercial.equipment_opportunity (opportunity_key)
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.equipment_opportunity.opportunity_key IS
          'Stable business/correlation key for equipment opportunity across source artifacts; not a primary key.'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_key")
    op.execute(
        """
        ALTER TABLE commercial.equipment_opportunity
          DROP COLUMN IF EXISTS opportunity_key
        """
    )
