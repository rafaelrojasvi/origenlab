"""Equipment opportunity_key correlation audit views.

Revision ID: 20260617_0029
Revises: 20260617_0028
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260617_0029"
down_revision: Union[str, Sequence[str], None] = "20260617_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMMERCIAL_VIEW = """
CREATE OR REPLACE VIEW commercial.v_equipment_opportunity_key_audit AS
SELECT
  eo.opportunity_key::text AS opportunity_key,
  count(*)::bigint AS row_count,
  count(DISTINCT eos.id)::bigint AS source_count,
  count(*) FILTER (WHERE eos.is_canonical)::bigint AS canonical_row_count,
  bool_or(eos.is_canonical) AS has_canonical,
  min(eos.synced_at) AS first_synced_at,
  max(eos.synced_at) AS last_synced_at,
  min(eo.close_at) AS first_close_at,
  max(eo.close_at) AS last_close_at,
  min(eo.codigo_licitacion)::text AS codigo_licitacion,
  min(eo.buyer) FILTER (
    WHERE eo.buyer IS NOT NULL AND btrim(eo.buyer) <> ''
  )::text AS sample_buyer,
  min(eo.extra_json ->> 'title') FILTER (
    WHERE eo.extra_json ->> 'title' IS NOT NULL AND btrim(eo.extra_json ->> 'title') <> ''
  )::text AS sample_title,
  min(eo.equipment_category) FILTER (
    WHERE eo.equipment_category IS NOT NULL AND btrim(eo.equipment_category) <> ''
  )::text AS sample_equipment_category,
  coalesce(
    array_agg(DISTINCT eos.artifact_basename ORDER BY eos.artifact_basename) FILTER (
      WHERE eos.artifact_basename IS NOT NULL AND btrim(eos.artifact_basename) <> ''
    ),
    ARRAY[]::text[]
  ) AS source_artifacts,
  coalesce(
    array_agg(DISTINCT eos.canonical_reason ORDER BY eos.canonical_reason) FILTER (
      WHERE eos.canonical_reason IS NOT NULL AND btrim(eos.canonical_reason) <> ''
    ),
    ARRAY[]::text[]
  ) AS canonical_reasons
FROM commercial.equipment_opportunity eo
JOIN commercial.equipment_opportunity_source eos ON eos.id = eo.source_id
GROUP BY eo.opportunity_key
"""

_API_VIEW = """
CREATE OR REPLACE VIEW api.v_equipment_opportunity_key_audit AS
SELECT
  opportunity_key,
  row_count,
  source_count,
  canonical_row_count,
  has_canonical,
  first_synced_at,
  last_synced_at,
  first_close_at,
  last_close_at,
  codigo_licitacion,
  sample_buyer,
  sample_title,
  sample_equipment_category,
  source_artifacts,
  canonical_reasons
FROM commercial.v_equipment_opportunity_key_audit
"""


def upgrade() -> None:
    op.execute(_COMMERCIAL_VIEW)
    op.execute(_API_VIEW)
    op.execute(
        """
        COMMENT ON VIEW commercial.v_equipment_opportunity_key_audit IS
          'Correlation audit: repeated opportunity_key values across source loads (not unique).'
        """
    )
    op.execute(
        """
        COMMENT ON VIEW api.v_equipment_opportunity_key_audit IS
          'Read-only API audit view for repeated equipment opportunity_key values.'
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS api.v_equipment_opportunity_key_audit")
    op.execute("DROP VIEW IF EXISTS commercial.v_equipment_opportunity_key_audit")
