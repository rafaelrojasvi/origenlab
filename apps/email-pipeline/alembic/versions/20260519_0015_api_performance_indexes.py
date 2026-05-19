"""API performance indexes (DB-1).

Revision ID: 20260519_0015
Revises: 20260519_0014
Create Date: 2026-05-19

Non-destructive optional indexes for api read paths.
DDL only; no data migration.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0015"
down_revision: Union[str, Sequence[str], None] = "20260519_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_archive_emails_canonical_sent
          ON archive.emails (date_iso DESC NULLS LAST)
          WHERE lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'
            AND folder IN ('[Gmail]/Enviados', '[Gmail]/Sent Mail')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_warm_case_open
          ON commercial.warm_case (last_activity_at DESC)
          WHERE closed_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_warm_case_open")
    op.execute("DROP INDEX IF EXISTS idx_archive_emails_canonical_sent")
