"""Lead research read-model mirror (Phase 10D).

Revision ID: 20260528_0021
Revises: 20260528_0020
Create Date: 2026-05-28

Populated from SQLite lead_research_* via sync_lead_research_postgres_mirror (opt-in).
No Gmail URLs, file paths, RUTs, or bank details.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260528_0021"
down_revision: Union[str, Sequence[str], None] = "20260528_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS lead_intel")
    op.execute(
        """
        COMMENT ON SCHEMA lead_intel IS
          'Redacted new-customer prospect research for operator dashboard (read-only).'
        """
    )

    op.execute(
        """
        CREATE TABLE lead_intel.prospect (
          prospect_key TEXT PRIMARY KEY,
          organization_name TEXT NOT NULL,
          contact_name TEXT,
          email TEXT,
          domain TEXT,
          sector TEXT,
          region TEXT,
          buyer_type TEXT,
          likely_need TEXT,
          product_angle TEXT,
          evidence_url TEXT,
          evidence_note TEXT,
          source TEXT,
          final_score INTEGER NOT NULL DEFAULT 0,
          confidence TEXT,
          classification TEXT NOT NULL,
          spanish_message_angle TEXT,
          risk_flags TEXT,
          block_or_review_reason TEXT,
          recommended_next_action TEXT,
          status TEXT NOT NULL,
          campaign_bucket TEXT,
          is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_lead_intel_prospect_classification ON lead_intel.prospect (classification)"
    )
    op.execute(
        "CREATE INDEX idx_lead_intel_prospect_status ON lead_intel.prospect (status)"
    )
    op.execute(
        "CREATE INDEX idx_lead_intel_prospect_score ON lead_intel.prospect (final_score DESC)"
    )
    op.execute(
        "CREATE INDEX idx_lead_intel_prospect_sector ON lead_intel.prospect (sector)"
    )

    op.execute(
        """
        CREATE TABLE lead_intel.evidence (
          id BIGSERIAL PRIMARY KEY,
          prospect_key TEXT NOT NULL REFERENCES lead_intel.prospect(prospect_key) ON DELETE CASCADE,
          evidence_kind TEXT NOT NULL DEFAULT 'public_url',
          evidence_url TEXT,
          evidence_note TEXT,
          source TEXT,
          confidence TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_lead_intel_evidence_key ON lead_intel.evidence (prospect_key)"
    )

    op.execute(
        """
        CREATE TABLE lead_intel.recommendation (
          prospect_key TEXT PRIMARY KEY REFERENCES lead_intel.prospect(prospect_key) ON DELETE CASCADE,
          campaign_bucket TEXT,
          recommended_message_angle TEXT,
          recommended_next_action TEXT,
          why_this_lead TEXT,
          suggested_subject TEXT,
          suggested_body_preview TEXT,
          safety_note TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE lead_intel.block_reason (
          id BIGSERIAL PRIMARY KEY,
          prospect_key TEXT NOT NULL REFERENCES lead_intel.prospect(prospect_key) ON DELETE CASCADE,
          reason_code TEXT NOT NULL,
          reason_label TEXT,
          synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_lead_intel_block_reason_key ON lead_intel.block_reason (prospect_key)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_intel.block_reason")
    op.execute("DROP TABLE IF EXISTS lead_intel.recommendation")
    op.execute("DROP TABLE IF EXISTS lead_intel.evidence")
    op.execute("DROP TABLE IF EXISTS lead_intel.prospect")
    op.execute("DROP SCHEMA IF EXISTS lead_intel")
