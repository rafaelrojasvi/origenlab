"""Canonical Gmail email classification mirror for dashboard API.

Revision ID: 20260518_0009
Revises: 20260517_0008
Create Date: 2026-05-18

Populated by dashboard_postgres_sync after mart/outbound loaders (read-only SQLite QA).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260518_0009"
down_revision: Union[str, Sequence[str], None] = "20260517_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE reporting.email_classification_canonical (
          email_id BIGINT PRIMARY KEY,
          sync_run_id BIGINT,
          date_iso TEXT,
          folder TEXT,
          from_addr TEXT,
          to_addrs TEXT,
          subject TEXT,
          predicted_label TEXT NOT NULL,
          categories_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          confidence TEXT NOT NULL,
          ambiguous BOOLEAN NOT NULL DEFAULT FALSE,
          recommended_action TEXT NOT NULL,
          etiqueta_ui TEXT NOT NULL,
          evidence TEXT,
          source_scope TEXT NOT NULL DEFAULT 'canonical',
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_reporting_email_classification_canonical_date
          ON reporting.email_classification_canonical (date_iso DESC NULLS LAST)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_reporting_email_classification_canonical_label
          ON reporting.email_classification_canonical (predicted_label)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_reporting_email_classification_canonical_action
          ON reporting.email_classification_canonical (recommended_action)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reporting.email_classification_canonical")
