"""Dashboard-oriented SQL views (recreated when schema layers are ensured).

Boundary: view definitions live here but encode **leads** semantics (e.g. ``sql_upstream_active``), so
this module couples mart-style reporting to the lead pipeline. Refresh via
``refresh_lead_match_summary_view`` / ``migrate_sqlite_schema`` — see ``sqlite_migrate``.
"""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.lead_upstream_reconcile import sql_upstream_active

# Exclude soft-retired leads (missing from current external_leads_raw snapshot).
_UPSTREAM_ACTIVE_LM = sql_upstream_active("LM")

# Core: no dependency on lead_account tables (match_leads may run before account rollup).
VIEW_LEAD_MATCH_SUMMARY_CORE = f"""
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
  LM.upstream_sync_state,
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
WHERE {_UPSTREAM_ACTIVE_LM}
"""

# Full: includes lead account rollup when those tables exist.
VIEW_LEAD_MATCH_SUMMARY_FULL = f"""
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
  LM.upstream_sync_state,
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
WHERE {_UPSTREAM_ACTIVE_LM}
"""

# Columns referenced by v_lead_match_summary (Phase 1+ match metadata included).
_LEAD_MASTER_COLS = frozenset(
    {
        "id",
        "source_name",
        "source_record_id",
        "org_name",
        "contact_name",
        "email",
        "email_norm",
        "domain_norm",
        "org_name_norm",
        "status",
        "upstream_sync_state",
        "priority_score",
    }
)
_ORG_MATCH_COLS = frozenset(
    {
        "id",
        "lead_id",
        "matched_domain",
        "matched_org_name",
        "match_type",
        "confidence_score",
        "evidence_json",
        "pipeline_run_id",
    }
)
_CONTACT_MATCH_COLS = frozenset(
    {
        "id",
        "lead_id",
        "matched_contact_email",
        "matched_contact_name",
        "matched_domain",
        "match_type",
        "confidence_score",
        "evidence_json",
        "pipeline_run_id",
    }
)
_ACCOUNT_MEMBERSHIP_COLS = frozenset({"lead_id", "lead_account_id"})
_ACCOUNT_MASTER_COLS = frozenset({"id", "canonical_name", "primary_domain"})


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return {str(row[1]) for row in cur.fetchall()}


def _has_columns(conn: sqlite3.Connection, table: str, required: frozenset[str]) -> bool:
    if not _table_exists(conn, table):
        return False
    cols = _column_names(conn, table)
    return required <= cols


def refresh_lead_match_summary_view(conn: sqlite3.Connection) -> str:
    """Replace v_lead_match_summary if prerequisites are met.

    Does not DROP the existing view unless a new view can be created (transactional).

    Returns:
        ok | skipped_no_lead_master | skipped_no_contacts_table |
        skipped_missing_prereq_columns | failed
    """
    if not _table_exists(conn, "lead_master"):
        return "skipped_no_lead_master"
    if not _table_exists(conn, "lead_matches_existing_contacts"):
        return "skipped_no_contacts_table"

    if not _has_columns(conn, "lead_master", _LEAD_MASTER_COLS):
        return "skipped_missing_prereq_columns"
    if not _has_columns(conn, "lead_matches_existing_orgs", _ORG_MATCH_COLS):
        return "skipped_missing_prereq_columns"
    if not _has_columns(conn, "lead_matches_existing_contacts", _CONTACT_MATCH_COLS):
        return "skipped_missing_prereq_columns"

    has_account_tables = _table_exists(conn, "lead_account_membership") and _table_exists(
        conn, "lead_account_master"
    )
    use_full = (
        has_account_tables
        and _has_columns(conn, "lead_account_membership", _ACCOUNT_MEMBERSHIP_COLS)
        and _has_columns(conn, "lead_account_master", _ACCOUNT_MASTER_COLS)
    )
    sql = VIEW_LEAD_MATCH_SUMMARY_FULL if use_full else VIEW_LEAD_MATCH_SUMMARY_CORE

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP VIEW IF EXISTS v_lead_match_summary")
        conn.execute(sql.strip())
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
        return "failed"
    return "ok"
