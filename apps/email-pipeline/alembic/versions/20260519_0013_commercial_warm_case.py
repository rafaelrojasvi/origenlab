"""Commercial warm_case tables (DB-1).

Revision ID: 20260519_0013
Revises: 20260519_0012
Create Date: 2026-05-19

See reports/out/active/current/db1_commercial_case_model_spec_20260519.md
Uses warm_case* names (avoids PostgreSQL reserved word CASE).
DDL only; no data migration.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0013"
down_revision: Union[str, Sequence[str], None] = "20260519_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE commercial.warm_case (
          id BIGSERIAL PRIMARY KEY,
          case_key TEXT NOT NULL,
          title TEXT NOT NULL,
          account_name TEXT,
          primary_contact_email TEXT NOT NULL,
          primary_domain TEXT,
          category TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open',
          next_action TEXT,
          equipment_signal TEXT,
          last_activity_at TIMESTAMPTZ NOT NULL,
          last_email_id BIGINT,
          opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          closed_at TIMESTAMPTZ,
          source TEXT NOT NULL DEFAULT 'warm_queue_promotion',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_by TEXT,

          CONSTRAINT uq_warm_case_case_key UNIQUE (case_key),
          CONSTRAINT chk_warm_case_category CHECK (
            category IN (
              'client_reply', 'supplier_reply', 'quote_sent',
              'waiting_supplier', 'waiting_client', 'bounce', 'opportunity'
            )
          ),
          CONSTRAINT chk_warm_case_status CHECK (
            status IN ('new', 'open', 'waiting', 'quoted', 'problem')
          ),
          CONSTRAINT chk_warm_case_email_nonempty CHECK (
            length(trim(primary_contact_email)) > 0
            AND position('@' in primary_contact_email) > 0
          )
        )
        """
    )
    op.execute(
        """
        COMMENT ON TABLE commercial.warm_case IS
          'Durable warm commercial thread/case for dashboard. Not a full CRM. Populated by promotion job from SQLite queue.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.warm_case.last_email_id IS
          'Latest archive.emails id (mirror); nullable if email not yet in archive mirror.'
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_last_activity
          ON commercial.warm_case (last_activity_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_status_activity
          ON commercial.warm_case (status, last_activity_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_contact_email
          ON commercial.warm_case (lower(primary_contact_email))
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_domain
          ON commercial.warm_case (primary_domain)
        """
    )

    op.execute(
        """
        CREATE TABLE commercial.warm_case_linked_email (
          case_id BIGINT NOT NULL REFERENCES commercial.warm_case(id) ON DELETE CASCADE,
          email_id BIGINT NOT NULL,
          link_role TEXT NOT NULL DEFAULT 'thread',
          linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          linked_by TEXT,

          PRIMARY KEY (case_id, email_id),
          CONSTRAINT chk_warm_case_linked_email_role CHECK (
            link_role IN ('thread', 'attachment', 'manual')
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_linked_email_email_id
          ON commercial.warm_case_linked_email (email_id)
        """
    )

    op.execute(
        """
        CREATE TABLE commercial.warm_case_status_history (
          id BIGSERIAL PRIMARY KEY,
          case_id BIGINT NOT NULL REFERENCES commercial.warm_case(id) ON DELETE CASCADE,
          from_status TEXT,
          to_status TEXT NOT NULL,
          reason TEXT,
          changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          changed_by TEXT,

          CONSTRAINT chk_warm_case_status_history_to CHECK (
            to_status IN ('new', 'open', 'waiting', 'quoted', 'problem')
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_status_history_case_changed
          ON commercial.warm_case_status_history (case_id, changed_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE commercial.warm_case_event (
          id BIGSERIAL PRIMARY KEY,
          case_id BIGINT NOT NULL REFERENCES commercial.warm_case(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by TEXT,

          CONSTRAINT chk_warm_case_event_type CHECK (
            event_type IN ('note', 'assign', 'link_email', 'promote', 'status_change')
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_event_case_created
          ON commercial.warm_case_event (case_id, created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE commercial.warm_case_equipment_signal (
          case_id BIGINT PRIMARY KEY REFERENCES commercial.warm_case(id) ON DELETE CASCADE,
          equipment_category TEXT,
          codigo_licitacion TEXT,
          opportunity_id BIGINT REFERENCES commercial.equipment_opportunity(id) ON DELETE SET NULL,
          signal_strength TEXT,
          details_json JSONB NOT NULL DEFAULT '{}'::jsonb,

          CONSTRAINT chk_warm_case_equipment_signal_strength CHECK (
            signal_strength IS NULL OR signal_strength IN ('weak', 'medium', 'strong')
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_warm_case_equipment_signal_opportunity
          ON commercial.warm_case_equipment_signal (opportunity_id)
          WHERE opportunity_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_warm_case_equipment_signal_opportunity")
    op.execute("DROP TABLE IF EXISTS commercial.warm_case_equipment_signal")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_event_case_created")
    op.execute("DROP TABLE IF EXISTS commercial.warm_case_event")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_status_history_case_changed")
    op.execute("DROP TABLE IF EXISTS commercial.warm_case_status_history")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_linked_email_email_id")
    op.execute("DROP TABLE IF EXISTS commercial.warm_case_linked_email")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_domain")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_contact_email")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_status_activity")
    op.execute("DROP INDEX IF EXISTS idx_warm_case_last_activity")
    op.execute("DROP TABLE IF EXISTS commercial.warm_case")
