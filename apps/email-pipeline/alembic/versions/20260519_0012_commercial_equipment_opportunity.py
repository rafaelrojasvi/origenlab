"""Commercial equipment opportunity tables (DB-1).

Revision ID: 20260519_0012
Revises: 20260519_0011
Create Date: 2026-05-19

See reports/out/active/current/db1_equipment_opportunity_model_spec_20260519.md
DDL only; no data migration.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0012"
down_revision: Union[str, Sequence[str], None] = "20260519_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE commercial.equipment_opportunity_source (
          id BIGSERIAL PRIMARY KEY,
          manifest_path TEXT NOT NULL,
          csv_path TEXT NOT NULL,
          date_suffix TEXT NOT NULL,
          campaign_mode TEXT,
          row_count INTEGER NOT NULL,
          file_sha256 TEXT,
          file_mtime TIMESTAMPTZ,
          is_canonical BOOLEAN NOT NULL DEFAULT FALSE,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          sync_run_id BIGINT REFERENCES reporting.dashboard_sync_run(id) ON DELETE SET NULL,
          loader_version TEXT NOT NULL DEFAULT 'db1_equipment_loader_v1',

          CONSTRAINT uq_equipment_opportunity_source_path UNIQUE (csv_path),
          CONSTRAINT chk_equipment_opportunity_source_row_count CHECK (row_count >= 0)
        )
        """
    )
    op.execute(
        """
        COMMENT ON TABLE commercial.equipment_opportunity_source IS
          'Provenance for equipment_first_operator_queue CSV loads. CSV remains legal artifact.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.equipment_opportunity_source.is_canonical IS
          'True when this source matches manifest canonical_files entry at load time.'
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_source_date_suffix
          ON commercial.equipment_opportunity_source (date_suffix DESC, synced_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_source_canonical
          ON commercial.equipment_opportunity_source (is_canonical, synced_at DESC)
          WHERE is_canonical = TRUE
        """
    )

    op.execute(
        """
        CREATE TABLE commercial.equipment_opportunity (
          id BIGSERIAL PRIMARY KEY,
          source_id BIGINT NOT NULL REFERENCES commercial.equipment_opportunity_source(id) ON DELETE CASCADE,
          priority_rank INTEGER,
          codigo_licitacion TEXT NOT NULL,
          buyer TEXT,
          region TEXT,
          close_date TEXT,
          close_at TIMESTAMPTZ,
          equipment_category TEXT,
          item_description TEXT,
          next_action TEXT,
          safe_channel TEXT,
          supplier_needed TEXT,
          contact_status TEXT,
          operator_note TEXT,
          dnr_flags TEXT,
          extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

          CONSTRAINT uq_equipment_opportunity_source_codigo UNIQUE (source_id, codigo_licitacion),
          CONSTRAINT chk_equipment_opportunity_codigo_nonempty CHECK (
            length(trim(codigo_licitacion)) > 0
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_source_priority
          ON commercial.equipment_opportunity (source_id, priority_rank NULLS LAST)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_close_at
          ON commercial.equipment_opportunity (close_at DESC NULLS LAST)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_category_close
          ON commercial.equipment_opportunity (equipment_category, close_at DESC NULLS LAST)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_next_action
          ON commercial.equipment_opportunity (next_action)
          WHERE next_action IS NOT NULL AND length(trim(next_action)) > 0
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_contact_status
          ON commercial.equipment_opportunity (contact_status)
        """
    )

    op.execute(
        """
        CREATE TABLE commercial.equipment_opportunity_status_event (
          id BIGSERIAL PRIMARY KEY,
          opportunity_id BIGINT NOT NULL REFERENCES commercial.equipment_opportunity(id) ON DELETE CASCADE,
          from_status TEXT,
          to_status TEXT NOT NULL,
          note TEXT,
          changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          changed_by TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_equipment_opportunity_status_event_opp
          ON commercial.equipment_opportunity_status_event (opportunity_id, changed_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_status_event_opp")
    op.execute("DROP TABLE IF EXISTS commercial.equipment_opportunity_status_event")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_contact_status")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_next_action")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_category_close")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_close_at")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_source_priority")
    op.execute("DROP TABLE IF EXISTS commercial.equipment_opportunity")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_source_canonical")
    op.execute("DROP INDEX IF EXISTS idx_equipment_opportunity_source_date_suffix")
    op.execute("DROP TABLE IF EXISTS commercial.equipment_opportunity_source")
