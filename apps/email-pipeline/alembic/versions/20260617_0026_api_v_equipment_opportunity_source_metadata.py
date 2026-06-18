"""Expose equipment source artifact metadata on api.v_equipment_opportunity.

Revision ID: 20260617_0026
Revises: 20260617_0025
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260617_0026"
down_revision: Union[str, Sequence[str], None] = "20260617_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_equipment_opportunity AS
        WITH latest_source AS (
          SELECT
            id,
            manifest_path,
            csv_path,
            date_suffix,
            campaign_mode,
            synced_at,
            source_kind,
            artifact_basename,
            canonical_reason
          FROM commercial.equipment_opportunity_source
          WHERE is_canonical = TRUE
          ORDER BY synced_at DESC, id DESC
          LIMIT 1
        )
        SELECT
          eo.id AS opportunity_id,
          eo.source_id,
          eo.priority_rank,
          eo.codigo_licitacion,
          eo.buyer,
          eo.region,
          eo.close_date,
          eo.close_at,
          eo.equipment_category,
          eo.item_description,
          eo.next_action,
          eo.safe_channel,
          eo.supplier_needed,
          eo.contact_status,
          eo.operator_note,
          ls.csv_path AS source_path,
          ls.campaign_mode,
          ls.synced_at,
          (eo.source_id = ls.id) AS is_canonical_source,
          eo.extra_json,
          ls.source_kind,
          ls.artifact_basename,
          ls.canonical_reason
        FROM commercial.equipment_opportunity eo
        JOIN commercial.equipment_opportunity_source src ON src.id = eo.source_id
        JOIN latest_source ls ON src.id = ls.id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_equipment_opportunity AS
        WITH latest_source AS (
          SELECT id, manifest_path, csv_path, date_suffix, campaign_mode, synced_at
          FROM commercial.equipment_opportunity_source
          WHERE is_canonical = TRUE
          ORDER BY synced_at DESC, id DESC
          LIMIT 1
        )
        SELECT
          eo.id AS opportunity_id,
          eo.source_id,
          eo.priority_rank,
          eo.codigo_licitacion,
          eo.buyer,
          eo.region,
          eo.close_date,
          eo.close_at,
          eo.equipment_category,
          eo.item_description,
          eo.next_action,
          eo.safe_channel,
          eo.supplier_needed,
          eo.contact_status,
          eo.operator_note,
          ls.csv_path AS source_path,
          ls.campaign_mode,
          ls.synced_at,
          (eo.source_id = ls.id) AS is_canonical_source,
          eo.extra_json
        FROM commercial.equipment_opportunity eo
        JOIN commercial.equipment_opportunity_source src ON src.id = eo.source_id
        JOIN latest_source ls ON src.id = ls.id
        """
    )
