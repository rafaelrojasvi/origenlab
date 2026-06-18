"""Current equipment opportunity read model: one canonical row per opportunity_key.

Revision ID: 20260617_0030
Revises: 20260617_0029
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260617_0030"
down_revision: Union[str, Sequence[str], None] = "20260617_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEW_UPGRADE = """
CREATE OR REPLACE VIEW api.v_equipment_opportunity_current AS
WITH canonical_rows AS (
  SELECT *
  FROM api.v_equipment_opportunity
  WHERE is_canonical_source = TRUE
),
ranked AS (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY opportunity_key
      ORDER BY
        priority_rank ASC NULLS LAST,
        close_at ASC NULLS LAST,
        synced_at DESC NULLS LAST,
        opportunity_id DESC
    ) AS rn
  FROM canonical_rows
)
SELECT
  opportunity_id,
  source_id,
  priority_rank,
  codigo_licitacion,
  buyer,
  region,
  close_date,
  close_at,
  equipment_category,
  item_description,
  next_action,
  safe_channel,
  supplier_needed,
  contact_status,
  operator_note,
  source_path,
  campaign_mode,
  synced_at,
  is_canonical_source,
  extra_json,
  source_kind,
  artifact_basename,
  canonical_reason,
  opportunity_key
FROM ranked
WHERE rn = 1
"""


def upgrade() -> None:
    op.execute(_VIEW_UPGRADE)
    op.execute(
        """
        COMMENT ON VIEW api.v_equipment_opportunity_current IS
          'Current equipment read model: one canonical row per opportunity_key for API/dashboard.'
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS api.v_equipment_opportunity_current")
