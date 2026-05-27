"""Load redacted lead research rows from SQLite for Postgres mirror."""

from __future__ import annotations

import sqlite3
from typing import Any

from origenlab_email_pipeline.lead_research.lead_research_mirror_safety import (
    assert_mirror_row_safe,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import lead_research_tables_exist


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row)))


def load_lead_research_mirror_payload(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    if not lead_research_tables_exist(conn):
        return {"prospects": [], "evidence": [], "recommendations": [], "block_reasons": []}

    conn.row_factory = sqlite3.Row
    prospects: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT prospect_key, organization_name, contact_name, email, domain,
               sector, region, buyer_type, likely_need, product_angle,
               evidence_url, evidence_note, source, final_score, confidence,
               classification, spanish_message_angle, risk_flags,
               block_or_review_reason, recommended_next_action, status,
               campaign_bucket, is_blocked
        FROM lead_research_prospect
        WHERE is_active = 1
        ORDER BY final_score DESC, organization_name
        """
    ):
        d = _row_dict(row)
        d["is_blocked"] = bool(int(d.get("is_blocked") or 0))
        assert_mirror_row_safe(d, table="prospect")
        prospects.append(d)

    evidence: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.prospect_key, e.evidence_kind, e.evidence_url, e.evidence_note, e.source, e.confidence
        FROM lead_research_evidence e
        JOIN lead_research_prospect p ON p.id = e.prospect_id
        WHERE p.is_active = 1
        ORDER BY p.prospect_key, e.id
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="evidence")
        evidence.append(d)

    recommendations: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.prospect_key, r.campaign_bucket, r.recommended_message_angle,
               r.recommended_next_action, r.why_this_lead, r.suggested_subject,
               r.suggested_body_preview, r.safety_note
        FROM lead_research_recommendation r
        JOIN lead_research_prospect p ON p.id = r.prospect_id
        WHERE p.is_active = 1
        ORDER BY p.prospect_key
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="recommendation")
        recommendations.append(d)

    block_reasons: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT p.prospect_key, b.reason_code, b.reason_label
        FROM lead_research_block_reason b
        JOIN lead_research_prospect p ON p.id = b.prospect_id
        WHERE p.is_active = 1
        ORDER BY p.prospect_key, b.id
        """
    ):
        d = _row_dict(row)
        assert_mirror_row_safe(d, table="block_reason")
        block_reasons.append(d)

    return {
        "prospects": prospects,
        "evidence": evidence,
        "recommendations": recommendations,
        "block_reasons": block_reasons,
    }
