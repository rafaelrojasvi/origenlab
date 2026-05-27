"""Read-only redacted lead research prospects (Postgres lead_intel.* mirror)."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, fetch_one, table_exists
from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import DEFAULT_MAX_LIMIT
from origenlab_email_pipeline.postgres_dashboard_api.schemas import (
    LEAD_RESEARCH_DISCLAIMER,
    LeadProspectBlockReasonRow,
    LeadProspectDetail,
    LeadProspectDetailResponse,
    LeadProspectEvidenceRow,
    LeadProspectListItem,
    LeadProspectRecommendationRow,
    LeadProspectsListResponse,
    LeadResearchSummaryResponse,
)

_PROSPECT_TABLE = ("lead_intel", "prospect")

_LIST_SELECT = """
SELECT
  prospect_key, organization_name, contact_name, email, domain,
  sector, region, buyer_type, product_angle, final_score, classification,
  status, spanish_message_angle, recommended_next_action, risk_flags,
  evidence_url, is_blocked, campaign_bucket
FROM lead_intel.prospect
"""


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), DEFAULT_MAX_LIMIT))


def _table_available(conn: Connection) -> bool:
    schema, table = _PROSPECT_TABLE
    return table_exists(conn, schema=schema, table=table)


def list_lead_prospects(
    conn: Connection,
    *,
    q: str | None = None,
    classification: str | None = None,
    sector: str | None = None,
    region: str | None = None,
    buyer_type: str | None = None,
    campaign_bucket: str | None = None,
    min_score: int | None = None,
    include_blocked: bool = False,
    limit: int = 50,
) -> LeadProspectsListResponse:
    if not _table_available(conn):
        return LeadProspectsListResponse(
            table_available=False,
            disclaimer=LEAD_RESEARCH_DISCLAIMER,
        )

    clauses: list[str] = []
    params: list[Any] = []

    if not include_blocked:
        clauses.append("is_blocked = FALSE")
    if classification:
        clauses.append("classification = %s")
        params.append(classification)
    if sector:
        clauses.append("sector ILIKE %s")
        params.append(f"%{sector}%")
    if region:
        clauses.append("region ILIKE %s")
        params.append(f"%{region}%")
    if buyer_type:
        clauses.append("buyer_type = %s")
        params.append(buyer_type)
    if campaign_bucket:
        clauses.append("campaign_bucket = %s")
        params.append(campaign_bucket)
    if min_score is not None:
        clauses.append("final_score >= %s")
        params.append(int(min_score))
    if q:
        clauses.append(
            "(organization_name ILIKE %s OR contact_name ILIKE %s OR email ILIKE %s OR domain ILIKE %s)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = _clamp_limit(limit)

    count_row = fetch_one(conn, f"SELECT COUNT(*) AS c FROM lead_intel.prospect {where}", params)
    total = int(count_row["c"]) if count_row else 0

    rows = fetch_all(
        conn,
        f"{_LIST_SELECT} {where} ORDER BY final_score DESC, organization_name LIMIT %s",
        [*params, lim],
    )
    items = [LeadProspectListItem.model_validate(dict(r)) for r in rows]
    return LeadProspectsListResponse(
        table_available=True,
        items=items,
        total=total,
        disclaimer=LEAD_RESEARCH_DISCLAIMER,
    )


def get_lead_prospect(conn: Connection, *, prospect_key: str) -> LeadProspectDetailResponse:
    if not _table_available(conn):
        return LeadProspectDetailResponse(table_available=False, disclaimer=LEAD_RESEARCH_DISCLAIMER)

    row = fetch_one(
        conn,
        """
        SELECT prospect_key, organization_name, contact_name, email, domain,
               sector, region, buyer_type, likely_need, product_angle,
               evidence_url, evidence_note, source, final_score, confidence,
               classification, spanish_message_angle, risk_flags,
               block_or_review_reason, recommended_next_action, status,
               campaign_bucket, is_blocked
        FROM lead_intel.prospect
        WHERE prospect_key = %s
        LIMIT 1
        """,
        [prospect_key],
    )
    if not row:
        return LeadProspectDetailResponse(table_available=True, disclaimer=LEAD_RESEARCH_DISCLAIMER)

    evidence_rows = fetch_all(
        conn,
        """
        SELECT evidence_kind, evidence_url, evidence_note, source, confidence
        FROM lead_intel.evidence
        WHERE prospect_key = %s
        ORDER BY id
        """,
        [prospect_key],
    )
    rec_row = fetch_one(
        conn,
        """
        SELECT campaign_bucket, recommended_message_angle, recommended_next_action,
               why_this_lead, suggested_subject, suggested_body_preview, safety_note
        FROM lead_intel.recommendation
        WHERE prospect_key = %s
        LIMIT 1
        """,
        [prospect_key],
    )
    block_rows = fetch_all(
        conn,
        """
        SELECT reason_code, reason_label
        FROM lead_intel.block_reason
        WHERE prospect_key = %s
        ORDER BY id
        """,
        [prospect_key],
    )

    return LeadProspectDetailResponse(
        table_available=True,
        prospect=LeadProspectDetail.model_validate(dict(row)),
        evidence=[LeadProspectEvidenceRow.model_validate(dict(r)) for r in evidence_rows],
        recommendation=(
            LeadProspectRecommendationRow.model_validate(dict(rec_row)) if rec_row else None
        ),
        block_reasons=[LeadProspectBlockReasonRow.model_validate(dict(r)) for r in block_rows],
        disclaimer=LEAD_RESEARCH_DISCLAIMER,
    )


def get_lead_research_summary(conn: Connection) -> LeadResearchSummaryResponse:
    if not _table_available(conn):
        return LeadResearchSummaryResponse(table_available=False, disclaimer=LEAD_RESEARCH_DISCLAIMER)

    agg = fetch_one(
        conn,
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE NOT is_blocked) AS review_count,
          COUNT(*) FILTER (WHERE is_blocked) AS blocked_count,
          COUNT(*) FILTER (WHERE classification = 'net_new_safe_review') AS net_new_safe,
          COUNT(*) FILTER (WHERE classification = 'public_tender_review') AS public_tender_review,
          COUNT(*) FILTER (WHERE classification = 'same_domain_contacted_review') AS same_domain_review,
          COUNT(*) FILTER (WHERE classification = 'research_only_contact_needed') AS research_needed
        FROM lead_intel.prospect
        """,
        [],
    )
    if not agg:
        return LeadResearchSummaryResponse(table_available=True, disclaimer=LEAD_RESEARCH_DISCLAIMER)

    return LeadResearchSummaryResponse(
        table_available=True,
        total=int(agg["total"]),
        review_count=int(agg["review_count"]),
        blocked_count=int(agg["blocked_count"]),
        net_new_safe=int(agg["net_new_safe"]),
        public_tender_review=int(agg["public_tender_review"]),
        same_domain_review=int(agg["same_domain_review"]),
        research_needed=int(agg["research_needed"]),
        disclaimer=LEAD_RESEARCH_DISCLAIMER,
    )
