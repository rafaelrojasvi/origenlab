"""Create PostgreSQL schemas and ops.pipeline_* tables only.

Revision ID: 20260419_0001
Revises:
Create Date: 2026-04-19

See docs/pipeline/POSTGRES_SCHEMA_TARGET_V1.md and POSTGRES_SCHEMA_RECONCILIATION_V1.md.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260419_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMAS: tuple[str, ...] = (
    "archive",
    "ops",
    "mart",
    "leads",
    "commercial",
    "outbound",
    "supplier",
    "reporting",
)


def upgrade() -> None:
    for name in _SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {name}")

    op.execute(
        """
        CREATE TABLE ops.pipeline_run (
          id BIGSERIAL PRIMARY KEY,
          started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ,
          script_name TEXT NOT NULL,
          argv_json JSONB,
          git_describe TEXT,
          notes TEXT,
          status TEXT NOT NULL DEFAULT 'running',
          error_message TEXT,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_ops_pipeline_run_started
          ON ops.pipeline_run(started_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_ops_pipeline_run_script
          ON ops.pipeline_run(script_name)
        """
    )
    op.execute(
        """
        CREATE TABLE ops.pipeline_kv (
          kv_key TEXT PRIMARY KEY,
          value_json JSONB,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.pipeline_kv")
    op.execute("DROP TABLE IF EXISTS ops.pipeline_run")
    # Drop placeholder schemas using plain DROP SCHEMA: if a later migration added objects to a
    # schema, PostgreSQL will reject the drop so downgrade fails instead of removing extra tables.
    for name in reversed(_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {name}")
