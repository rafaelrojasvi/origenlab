"""Dashboard-oriented SQL views (recreated when schema layers are ensured)."""

from __future__ import annotations

import sqlite3

# Core: no dependency on lead_account tables (match_leads may run before account rollup).
VIEW_LEAD_MATCH_SUMMARY_CORE = """
CREATE VIEW v_lead_match_summary AS
SELECT
  LM.id AS lead_id,
  LM.source_name,
  LM.source_record_id,
  LM.org_name,
  LM.contact_name,
  LM.email,
  LM.email_norm,
  LM.domain_norm,
  LM.org_name_norm,
  LM.status,
  LM.priority_score,
  LO.id AS org_match_id,
  LO.matched_domain AS org_match_domain,
  LO.matched_org_name AS org_match_org_name,
  LO.match_type AS org_match_type,
  LO.confidence_score AS org_match_confidence,
  LO.evidence_json AS org_match_evidence,
  LO.pipeline_run_id AS org_match_run_id,
  LC.id AS contact_match_id,
  LC.matched_contact_email,
  LC.matched_contact_name,
  LC.matched_domain AS contact_match_matched_domain,
  LC.match_type AS contact_match_type,
  LC.confidence_score AS contact_match_confidence,
  LC.evidence_json AS contact_match_evidence,
  LC.pipeline_run_id AS contact_match_run_id,
  CAST(NULL AS INTEGER) AS lead_account_id,
  CAST(NULL AS TEXT) AS lead_account_name,
  CAST(NULL AS TEXT) AS lead_account_domain,
  CASE WHEN LO.lead_id IS NOT NULL OR LC.lead_id IS NOT NULL THEN 1 ELSE 0 END AS known_in_archive_any,
  CASE WHEN LO.lead_id IS NOT NULL THEN 1 ELSE 0 END AS known_by_org,
  CASE WHEN LC.lead_id IS NOT NULL THEN 1 ELSE 0 END AS known_by_contact,
  0 AS has_lead_account
FROM lead_master LM
LEFT JOIN lead_matches_existing_orgs LO ON LM.id = LO.lead_id
LEFT JOIN lead_matches_existing_contacts LC ON LM.id = LC.lead_id
"""

# Full: includes lead account rollup when those tables exist.
VIEW_LEAD_MATCH_SUMMARY_FULL = """
CREATE VIEW v_lead_match_summary AS
SELECT
  LM.id AS lead_id,
  LM.source_name,
  LM.source_record_id,
  LM.org_name,
  LM.contact_name,
  LM.email,
  LM.email_norm,
  LM.domain_norm,
  LM.org_name_norm,
  LM.status,
  LM.priority_score,
  LO.id AS org_match_id,
  LO.matched_domain AS org_match_domain,
  LO.matched_org_name AS org_match_org_name,
  LO.match_type AS org_match_type,
  LO.confidence_score AS org_match_confidence,
  LO.evidence_json AS org_match_evidence,
  LO.pipeline_run_id AS org_match_run_id,
  LC.id AS contact_match_id,
  LC.matched_contact_email,
  LC.matched_contact_name,
  LC.matched_domain AS contact_match_matched_domain,
  LC.match_type AS contact_match_type,
  LC.confidence_score AS contact_match_confidence,
  LC.evidence_json AS contact_match_evidence,
  LC.pipeline_run_id AS contact_match_run_id,
  LAM.lead_account_id AS lead_account_id,
  LAC.canonical_name AS lead_account_name,
  LAC.primary_domain AS lead_account_domain,
  CASE WHEN LO.lead_id IS NOT NULL OR LC.lead_id IS NOT NULL THEN 1 ELSE 0 END AS known_in_archive_any,
  CASE WHEN LO.lead_id IS NOT NULL THEN 1 ELSE 0 END AS known_by_org,
  CASE WHEN LC.lead_id IS NOT NULL THEN 1 ELSE 0 END AS known_by_contact,
  CASE WHEN LAM.lead_id IS NOT NULL THEN 1 ELSE 0 END AS has_lead_account
FROM lead_master LM
LEFT JOIN lead_matches_existing_orgs LO ON LM.id = LO.lead_id
LEFT JOIN lead_matches_existing_contacts LC ON LM.id = LC.lead_id
LEFT JOIN lead_account_membership LAM ON LM.id = LAM.lead_id
LEFT JOIN lead_account_master LAC ON LAM.lead_account_id = LAC.id
"""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def refresh_lead_match_summary_view(conn: sqlite3.Connection) -> None:
    """Drop and recreate v_lead_match_summary if base tables exist."""
    if not _table_exists(conn, "lead_master"):
        return
    conn.execute("DROP VIEW IF EXISTS v_lead_match_summary")
    has_accounts = _table_exists(conn, "lead_account_membership") and _table_exists(
        conn, "lead_account_master"
    )
    has_contacts = _table_exists(conn, "lead_matches_existing_contacts")
    if not has_contacts:
        return
    sql = VIEW_LEAD_MATCH_SUMMARY_FULL if has_accounts else VIEW_LEAD_MATCH_SUMMARY_CORE
    conn.execute(sql)
    conn.commit()
