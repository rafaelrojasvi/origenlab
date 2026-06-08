"""Add role_category to commercial.warm_case and expose via api.v_warm_case.

Revision ID: 20260607_0023
Revises: 20260531_0022
Create Date: 2026-06-07

Preserves precise warm-case role taxonomy in Postgres mirror while keeping legacy
``category`` column for CHECK compatibility.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260607_0023"
down_revision: Union[str, Sequence[str], None] = "20260531_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_CATEGORIES_SQL = """
  'client_opportunity',
  'client_response',
  'supplier_quote_received',
  'supplier_followup',
  'payment_admin',
  'logistics_admin',
  'internal_admin',
  'system_noise',
  'bounce_problem',
  'deal_evidence_candidate',
  'quote_sent',
  'waiting_supplier',
  'waiting_client',
  'campaign_outreach',
  'waiting_campaign_reply',
  'auto_acknowledgement'
"""


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE commercial.warm_case
          ADD COLUMN IF NOT EXISTS role_category TEXT NULL
        """
    )
    op.execute(
        f"""
        ALTER TABLE commercial.warm_case
          ADD CONSTRAINT chk_warm_case_role_category CHECK (
            role_category IS NULL OR role_category IN ({_ROLE_CATEGORIES_SQL})
          )
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN commercial.warm_case.role_category IS
          'Precise warm-case role taxonomy (Phase 7A). Legacy category column retains CHECK-compatible storage values.'
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_warm_case AS
        SELECT
          ('case:' || c.id::text) AS case_id,
          c.last_email_id,
          c.last_activity_at AS last_seen_at,
          COALESCE(c.account_name, '') AS account_name,
          c.primary_contact_email AS contact_email,
          c.title AS subject,
          COALESCE(c.role_category, c.category) AS category,
          c.status,
          COALESCE(c.next_action, '') AS next_action,
          COALESCE(es.equipment_category, c.equipment_signal, '') AS equipment_signal,
          LEFT(COALESCE(c.title, ''), 280) AS snippet,
          NULL::TEXT AS gmail_url
        FROM commercial.warm_case c
        LEFT JOIN commercial.warm_case_equipment_signal es ON es.case_id = c.id
        WHERE c.closed_at IS NULL
          AND lower(trim(COALESCE(c.category, ''))) <> 'bounce'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_warm_case AS
        SELECT
          ('case:' || c.id::text) AS case_id,
          c.last_email_id,
          c.last_activity_at AS last_seen_at,
          COALESCE(c.account_name, '') AS account_name,
          c.primary_contact_email AS contact_email,
          c.title AS subject,
          c.category,
          c.status,
          COALESCE(c.next_action, '') AS next_action,
          COALESCE(es.equipment_category, c.equipment_signal, '') AS equipment_signal,
          LEFT(COALESCE(c.title, ''), 280) AS snippet,
          NULL::TEXT AS gmail_url
        FROM commercial.warm_case c
        LEFT JOIN commercial.warm_case_equipment_signal es ON es.case_id = c.id
        WHERE c.closed_at IS NULL
          AND lower(trim(COALESCE(c.category, ''))) <> 'bounce'
        """
    )
    op.execute(
        """
        ALTER TABLE commercial.warm_case
          DROP CONSTRAINT IF EXISTS chk_warm_case_role_category
        """
    )
    op.execute(
        """
        ALTER TABLE commercial.warm_case
          DROP COLUMN IF EXISTS role_category
        """
    )
