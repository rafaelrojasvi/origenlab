"""read/leads_browse: availability, SQL shape, filters, account rollup."""

from __future__ import annotations

import sqlite3

import pandas as pd

from origenlab_email_pipeline.business_mart_schema import BUSINESS_MART_SCHEMA_SQL
from origenlab_email_pipeline.lead_accounts_schema import ensure_lead_account_tables
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base, finalize_lead_master_source_keys
from origenlab_email_pipeline.read.leads_browse import (
    LeadBrowseFilters,
    build_leads_browse_query,
    fetch_lead_account_rollups_df,
    fetch_leads_browse_df,
    lead_browse_filter_options,
    lead_browse_ready,
)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def test_lead_browse_ready_missing_table() -> None:
    conn = _conn()
    ok, reason = lead_browse_ready(conn)
    assert ok is False
    assert reason == "missing_lead_master"


def test_fetch_leads_empty_without_lead_master() -> None:
    conn = _conn()
    df = fetch_leads_browse_df(conn)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_build_query_no_match_joins_has_no_orgm_alias() -> None:
    q = build_leads_browse_query(
        include_org_contact_matches=False,
        include_org_master=False,
        include_lead_accounts=False,
    )
    assert "orgm." not in q
    assert "FROM lead_master lm" in q


def test_build_query_with_matches_includes_best_org_join_rule() -> None:
    q = build_leads_browse_query(
        include_org_contact_matches=True,
        include_org_master=False,
        include_lead_accounts=False,
    )
    assert "orgm" in q
    assert "MIN(m2.id)" in q
    assert "lead_matches_existing_contacts" in q


def test_build_query_with_contact_research_includes_lcr_join() -> None:
    q = build_leads_browse_query(
        include_org_contact_matches=False,
        include_org_master=False,
        include_lead_accounts=False,
        include_contact_research=True,
    )
    assert "lead_contact_research lcr" in q
    assert "lcr.lead_id" in q


def test_build_query_without_contact_research_uses_null_casts() -> None:
    q = build_leads_browse_query(
        include_org_contact_matches=False,
        include_org_master=False,
        include_lead_accounts=False,
        include_contact_research=False,
    )
    assert "lcr" not in q
    assert "contact_research_status" in q


def test_filter_options_empty_when_no_lead_master() -> None:
    conn = _conn()
    opts = lead_browse_filter_options(conn)
    assert opts["fit_bucket"] == []


def _minimal_leads_db(with_org_master: bool = False) -> sqlite3.Connection:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    conn.executescript(
        """
        INSERT INTO lead_master (
          id, source_name, source_record_id, org_name, contact_name, email,
          fit_bucket, priority_score, status, next_action, review_owner,
          evidence_summary, notes, first_seen_at, last_seen_at
        ) VALUES
          (1, 'src_a', 'r1', 'Org One', 'C1', 'a@x.cl',
           'high_fit', 8.0, 'nuevo', '', 't1',
           'ev1', 'n1', '2024-01-01', '2024-02-01'),
          (2, 'src_b', 'r2', 'Org Two', NULL, NULL,
           'medium_fit', 3.0, 'contactado', 'seguir', NULL,
           NULL, NULL, '2024-01-02', '2024-03-01'),
          (3, 'src_a', 'r3', 'Org Three', NULL, NULL,
           'low_fit', 1.0, 'nuevo', NULL, NULL,
           NULL, NULL, '2024-01-03', '2024-03-02');
        INSERT INTO lead_matches_existing_orgs (
          id, lead_id, matched_domain, matched_org_name, match_type, confidence_score, already_in_archive_flag
        ) VALUES
          (100, 1, 'x.cl', 'Org X', 'domain', 0.9, 1),
          (200, 1, 'y.cl', 'Stale pick', 'domain', 0.5, 0);
        INSERT INTO lead_matches_existing_contacts (
          id, lead_id, matched_contact_email, matched_contact_name, matched_domain,
          match_type, confidence_score, already_in_archive_flag, created_at
        ) VALUES
          (10, 2, 'p@z.cl', 'P', 'z.cl', 'email', 0.8, 1, '2024-01-01T00:00:00');
        """
    )
    if with_org_master:
        conn.executescript(BUSINESS_MART_SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO organization_master (
              domain, organization_name_guess, total_emails, last_seen_at, quote_email_count
            ) VALUES ('x.cl', 'Historical X', 42, '2024-06-01', 5)
            """
        )
    conn.commit()
    return conn


def test_fetch_leads_includes_research_columns() -> None:
    conn = _minimal_leads_db(with_org_master=False)
    conn.execute(
        """
        INSERT INTO lead_contact_research (
          lead_id, contact_research_status, resolved_domain, updated_at
        ) VALUES (1, 'investigar_contacto', 'x.cl', '2026-01-01')
        """
    )
    conn.commit()
    df = fetch_leads_browse_df(conn, LeadBrowseFilters(limit=100))
    r1 = df[df["lead_id"] == 1].iloc[0]
    assert r1["contact_research_status"] == "investigar_contacto"
    assert r1["research_resolved_domain"] == "x.cl"


def test_fetch_leads_one_row_per_lead_and_best_org_is_lower_id() -> None:
    conn = _minimal_leads_db(with_org_master=True)
    df = fetch_leads_browse_df(conn, LeadBrowseFilters(limit=100))
    assert len(df) == 3
    row1 = df[df["lead_id"] == 1].iloc[0]
    assert row1["org_match_domain"] == "x.cl"
    assert row1["org_match_org_name"] == "Org X"
    assert int(row1["known_in_archive_any"]) == 1
    assert row1["archive_org_total_emails"] == 42
    assert row1["archive_org_quote_emails"] == 5

    row2 = df[df["lead_id"] == 2].iloc[0]
    assert row2["contact_match_email"] == "p@z.cl"
    assert int(row2["known_in_archive_any"]) == 1

    row3 = df[df["lead_id"] == 3].iloc[0]
    assert row3["org_match_domain"] is None or pd.isna(row3["org_match_domain"])
    assert int(row3["known_in_archive_any"]) == 0


def test_filter_needs_action_only() -> None:
    conn = _minimal_leads_db()
    df = fetch_leads_browse_df(conn, LeadBrowseFilters(needs_action_only=True, limit=100))
    ids = set(df["lead_id"].tolist())
    assert ids == {1, 3}


def test_filter_archive_match_none() -> None:
    conn = _minimal_leads_db()
    df = fetch_leads_browse_df(conn, LeadBrowseFilters(archive_match="none", limit=100))
    assert set(df["lead_id"].tolist()) == {3}


def test_filter_archive_match_has() -> None:
    conn = _minimal_leads_db()
    df = fetch_leads_browse_df(conn, LeadBrowseFilters(archive_match="has", limit=100))
    assert set(df["lead_id"].tolist()) == {1, 2}


def test_filter_options_distinct() -> None:
    conn = _minimal_leads_db()
    opts = lead_browse_filter_options(conn)
    assert "high_fit" in opts["fit_bucket"]
    assert "src_a" in opts["source_name"]
    assert "nuevo" in opts["status"]


def test_lead_account_rollups_none_without_table() -> None:
    conn = _minimal_leads_db()
    assert fetch_lead_account_rollups_df(conn) is None


def test_lead_account_rollups_when_present() -> None:
    conn = _minimal_leads_db()
    ensure_lead_account_tables(conn)
    conn.execute(
        """
        INSERT INTO lead_account_master (
          account_dedupe_key, canonical_name, normalized_name, lead_count, source_count,
          quality_status, created_at, updated_at
        ) VALUES ('k1', 'Big Buyer', 'big buyer', 3, 1, 'ok', 't', 't')
        """
    )
    conn.commit()
    acc = fetch_lead_account_rollups_df(conn, limit=10)
    assert acc is not None
    assert len(acc) == 1
    assert acc.iloc[0]["canonical_name"] == "Big Buyer"
