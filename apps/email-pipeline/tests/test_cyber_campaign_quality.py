"""Cyber campaign Phase 1.1 — geography, org dedupe, Phase 10D net-new."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.campaigns.cyber_campaign_quality import (
    GEO_CHILE_OK,
    GEO_MANUAL_REVIEW,
    classify_geography,
    is_active_warm_sales_thread,
    dedupe_by_domain,
    enrich_priority_score,
    gather_lead_research_net_new,
    is_generic_mailbox,
)
from origenlab_email_pipeline.campaigns.cyber_campaign_types import (
    SEGMENT_NET_NEW,
    SEGMENT_PREVIOUS,
    SEGMENT_WARM,
    CyberCampaignRow,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import ensure_lead_research_tables
from origenlab_email_pipeline.leads.new_customer_research import CLASS_NET_NEW


def test_active_warm_thread_blocks_cesmec_and_hielscher() -> None:
    blocked, _ = is_active_warm_sales_thread(
        "juan-pablo.garcia@bureauveritas.com", organization="CESMEC"
    )
    assert blocked
    blocked2, _ = is_active_warm_sales_thread("marcos@hielscher.com", organization="Hielscher")
    assert blocked2


def test_classify_geography_cl_vs_foreign() -> None:
    ok, _ = classify_geography(
        "lab@test.cl",
        domain="test.cl",
        region="Región Metropolitana",
        organization="Lab Chile",
    )
    assert ok == GEO_CHILE_OK
    manual, reason = classify_geography(
        "easare@gsa.gov.gh",
        domain="gsa.gov.gh",
        organization="Gov Ghana",
    )
    assert manual == GEO_MANUAL_REVIEW
    assert "gh" in reason.lower() or "extranjero" in reason.lower()


def test_dedupe_by_domain_one_per_org() -> None:
    meta: dict = {}
    rows = [
        CyberCampaignRow(
            email="a@saval.cl",
            organization="Saval",
            contact_name="A",
            segment=SEGMENT_PREVIOUS,
            reason_for_inclusion="",
            product_angle="",
            suggested_subject="",
            suggested_message="",
            safety_status="eligible",
            exclusion_reason="",
            priority_score=100.0,
        ),
        CyberCampaignRow(
            email="b@saval.cl",
            organization="Saval",
            contact_name="B",
            segment=SEGMENT_PREVIOUS,
            reason_for_inclusion="",
            product_angle="",
            suggested_subject="",
            suggested_message="",
            safety_status="eligible",
            exclusion_reason="",
            priority_score=80.0,
        ),
    ]
    meta["a@saval.cl"] = {"domain": "saval.cl"}
    meta["b@saval.cl"] = {"domain": "saval.cl"}
    deduped, stats = dedupe_by_domain(rows, meta)
    assert stats["rows_before"] == 2
    assert stats["rows_after"] == 1
    assert deduped[0].email == "a@saval.cl"
    assert "b@saval.cl" in meta["a@saval.cl"]["secondary_contact_emails"]


def test_named_contact_scores_above_generic() -> None:
    named = CyberCampaignRow(
        email="juan@lab.cl",
        organization="Lab",
        contact_name="Juan",
        segment=SEGMENT_WARM,
        reason_for_inclusion="",
        product_angle="",
        suggested_subject="",
        suggested_message="",
        safety_status="eligible",
        exclusion_reason="",
        priority_score=50.0,
    )
    generic = CyberCampaignRow(
        email="info@lab.cl",
        organization="Lab",
        contact_name="",
        segment=SEGMENT_WARM,
        reason_for_inclusion="",
        product_angle="",
        suggested_subject="",
        suggested_message="",
        safety_status="eligible",
        exclusion_reason="",
        priority_score=50.0,
    )
    assert is_generic_mailbox("info@lab.cl")
    assert enrich_priority_score(named, {"domain": "lab.cl"}) > enrich_priority_score(
        generic, {"domain": "lab.cl"}
    )


def test_gather_lead_research_net_new_from_sqlite(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        ensure_lead_research_tables(conn)
        conn.execute(
            """
            INSERT INTO lead_research_batch (batch_key, source_name, row_count, created_at)
            VALUES ('t', 'test', 1, '2026-01-01')
            """
        )
        bid = conn.execute("SELECT id FROM lead_research_batch").fetchone()[0]
        conn.execute(
            """
            INSERT INTO lead_research_prospect (
              batch_id, prospect_key, organization_name, email, domain,
              classification, status, is_blocked, is_active, input_priority_score,
              final_score, created_at
            ) VALUES (
              ?, 'p1', 'Clínica Test', 'nuevo@clinica-test.cl', 'clinica-test.cl',
              ?, 'net_new_safe_review', 0, 1, 80, 90, '2026-01-01'
            )
            """,
            (bid, CLASS_NET_NEW),
        )
        conn.commit()
        rows = gather_lead_research_net_new(conn, review_csv=tmp_path / "missing.csv")
        assert len(rows) == 1
        assert rows[0]["email"] == "nuevo@clinica-test.cl"
    finally:
        conn.close()
