"""Expose payment/logistics warm cases in api.v_warm_case (status=problem allowed).

Revision ID: 20260524_0017
Revises: 20260519_0016
Create Date: 2026-05-24

Prior view excluded status=problem; promotion marks some bank/logistics rows problem
via suppression heuristics, hiding them from the dashboard entirely.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260524_0017"
down_revision: Union[str, Sequence[str], None] = "20260519_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        WHERE c.status IN ('new', 'open', 'waiting', 'quoted')
          AND c.closed_at IS NULL
        """
    )
