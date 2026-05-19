"""Read-only grants for origenlab_api_ro role (DB-1).

Revision ID: 20260519_0016
Revises: 20260519_0015
Create Date: 2026-05-19

Safe no-op when role origenlab_api_ro does not exist.
DDL only; no data migration.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0016"
down_revision: Union[str, Sequence[str], None] = "20260519_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'origenlab_api_ro') THEN
            GRANT USAGE ON SCHEMA api, mart, outbound, reporting, commercial TO origenlab_api_ro;
            GRANT SELECT ON ALL TABLES IN SCHEMA api TO origenlab_api_ro;
            ALTER DEFAULT PRIVILEGES IN SCHEMA api
              GRANT SELECT ON TABLES TO origenlab_api_ro;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'origenlab_api_ro') THEN
            REVOKE SELECT ON ALL TABLES IN SCHEMA api FROM origenlab_api_ro;
            REVOKE USAGE ON SCHEMA api, mart, outbound, reporting, commercial FROM origenlab_api_ro;
          END IF;
        END $$
        """
    )
