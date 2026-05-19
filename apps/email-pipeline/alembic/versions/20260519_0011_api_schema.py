"""Create api schema for read-only HTTP contracts (DB-1).

Revision ID: 20260519_0011
Revises: 20260519_0010
Create Date: 2026-05-19

See reports/out/active/current/db1_api_read_model_ddl_spec_20260519.md
DDL only; no data migration.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0011"
down_revision: Union[str, Sequence[str], None] = "20260519_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS api")
    op.execute(
        """
        COMMENT ON SCHEMA api IS
          'Read-only HTTP contracts for apps/api Postgres backend. No writes.'
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS api")
