"""Read-only lead browse: pipeline + archive linkage (neutral module; Streamlit S2).

Uses the same upstream-active and best-per-lead match semantics as lead exports (MIN match row id).

``lead_contact_research`` is joined when that table exists (operator enrichment; distinct from import fields).
Writes to enrichment are done only from the Streamlit app when ``ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW=1``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd
from pandas.errors import DatabaseError as PandasDatabaseError

from origenlab_email_pipeline.lead_export_queries import sql_upstream_active_lead_master

_SAFE_DISTINCT_COLS = frozenset({"fit_bucket", "status", "source_name"})


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def lead_browse_ready(conn: sqlite3.Connection) -> tuple[bool, str | None]:
    """Return (ok, reason_code) — reason when ``lead_master`` is missing."""
    if not _table_exists(conn, "lead_master"):
        return False, "missing_lead_master"
    return True, None


def _match_joins_available(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "lead_matches_existing_orgs") and _table_exists(
        conn, "lead_matches_existing_contacts"
    )


def _account_joins_available(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "lead_account_membership") and _table_exists(
        conn, "lead_account_master"
    )


_CONTACT_BEST_JOIN = """
LEFT JOIN (
  SELECT lead_id, MIN(id) AS pick_id
  FROM lead_matches_existing_contacts
  GROUP BY lead_id
) lcp ON lcp.lead_id = lm.id
LEFT JOIN lead_matches_existing_contacts lcm ON lcm.id = lcp.pick_id
"""


def _contact_best_join_sql() -> str:
    return _CONTACT_BEST_JOIN


def _sql_left_join_best_org_match_detail(alias_lm: str = "lm", alias_m: str = "orgm") -> str:
    """Same MIN(id) rule as exports, with columns needed for the Streamlit browse UI."""
    return (
        f"LEFT JOIN (\n"
        f"          SELECT m1.lead_id, m1.matched_org_name, m1.matched_domain, "
        f"m1.already_in_archive_flag, m1.match_type, m1.confidence_score\n"
        f"          FROM lead_matches_existing_orgs m1\n"
        f"          WHERE m1.id = (\n"
        f"            SELECT MIN(m2.id) FROM lead_matches_existing_orgs m2 "
        f"WHERE m2.lead_id = m1.lead_id\n"
        f"          )\n"
        f"        ) {alias_m} ON {alias_m}.lead_id = {alias_lm}.id"
    )


@dataclass(frozen=True)
class LeadBrowseFilters:
    """Filter state for the leads browse table (all optional restrictions)."""

    fit_buckets: tuple[str, ...] | None = None
    statuses: tuple[str, ...] | None = None
    sources: tuple[str, ...] | None = None
    archive_match: str = "any"  # any | has | none
    needs_action_only: bool = False
    limit: int = 2000


def lead_browse_filter_options(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Distinct filter values for upstream-active leads only."""
    opts: dict[str, list[str]] = {"fit_bucket": [], "status": [], "source_name": []}
    ok, _ = lead_browse_ready(conn)
    if not ok:
        return opts
    up = sql_upstream_active_lead_master("lm")
    for col in sorted(_SAFE_DISTINCT_COLS):
        try:
            rows = conn.execute(
                f"""
                SELECT DISTINCT TRIM(lm.{col}) AS v
                FROM lead_master lm
                WHERE {up}
                  AND TRIM(COALESCE(lm.{col}, '')) != ''
                ORDER BY 1
                LIMIT 500
                """
            ).fetchall()
            opts[col] = [str(r[0]) for r in rows if r[0] is not None]
        except sqlite3.Error:
            opts[col] = []
    return opts


def _validate_archive_match(value: str) -> str:
    v = (value or "any").strip().lower()
    if v in ("has", "none", "any"):
        return v
    return "any"


def build_leads_browse_query(
    *,
    include_org_contact_matches: bool,
    include_org_master: bool,
    include_lead_accounts: bool,
    include_contact_research: bool = False,
) -> str:
    """Build SELECT for lead browse; used by tests and ``fetch_leads_browse_df``."""
    up = sql_upstream_active_lead_master("lm")
    org_join = ""
    contact_join = ""
    archive_select = (
        ", CAST(NULL AS INTEGER) AS known_in_archive_any"
        ", CAST(NULL AS TEXT) AS org_match_domain"
        ", CAST(NULL AS TEXT) AS org_match_org_name"
        ", CAST(NULL AS TEXT) AS org_match_type"
        ", CAST(NULL AS REAL) AS org_match_confidence"
        ", CAST(NULL AS INTEGER) AS org_already_in_archive"
        ", CAST(NULL AS TEXT) AS contact_match_email"
        ", CAST(NULL AS TEXT) AS contact_match_type"
        ", CAST(NULL AS REAL) AS contact_match_confidence"
        ", CAST(NULL AS INTEGER) AS contact_already_in_archive"
    )
    account_select = (
        ", CAST(NULL AS INTEGER) AS lead_account_id"
        ", CAST(NULL AS TEXT) AS lead_account_name"
        ", CAST(NULL AS TEXT) AS lead_account_domain"
        ", CAST(NULL AS INTEGER) AS account_lead_count"
    )
    om_select = (
        ", CAST(NULL AS INTEGER) AS archive_org_total_emails"
        ", CAST(NULL AS TEXT) AS archive_org_last_seen"
        ", CAST(NULL AS INTEGER) AS archive_org_quote_emails"
    )
    research_join = ""
    research_select = """
        , CAST(NULL AS TEXT) AS contact_research_status
        , CAST(NULL AS TEXT) AS research_resolved_domain
        , CAST(NULL AS TEXT) AS research_resolved_contact_name
        , CAST(NULL AS TEXT) AS research_resolved_contact_email
        , CAST(NULL AS TEXT) AS research_contact_source
        , CAST(NULL AS TEXT) AS research_contact_notes
        , CAST(NULL AS TEXT) AS contact_research_updated_at
        , CAST(NULL AS TEXT) AS contact_research_updated_by
        """

    if include_org_contact_matches:
        org_join = _sql_left_join_best_org_match_detail("lm", "orgm")
        contact_join = _contact_best_join_sql()
        archive_select = """
        , CASE WHEN orgm.matched_domain IS NOT NULL OR lcm.matched_contact_email IS NOT NULL
               THEN 1 ELSE 0 END AS known_in_archive_any
        , orgm.matched_domain AS org_match_domain
        , orgm.matched_org_name AS org_match_org_name
        , orgm.match_type AS org_match_type
        , orgm.confidence_score AS org_match_confidence
        , orgm.already_in_archive_flag AS org_already_in_archive
        , lcm.matched_contact_email AS contact_match_email
        , lcm.match_type AS contact_match_type
        , lcm.confidence_score AS contact_match_confidence
        , lcm.already_in_archive_flag AS contact_already_in_archive
        """

    if include_lead_accounts:
        account_select = """
        , lac.id AS lead_account_id
        , lac.canonical_name AS lead_account_name
        , lac.primary_domain AS lead_account_domain
        , lac.lead_count AS account_lead_count
        """
        account_join = """
        LEFT JOIN (
          SELECT lead_id, MIN(id) AS pick_id
          FROM lead_account_membership
          GROUP BY lead_id
        ) lacp ON lacp.lead_id = lm.id
        LEFT JOIN lead_account_membership lam ON lam.id = lacp.pick_id
        LEFT JOIN lead_account_master lac ON lac.id = lam.lead_account_id
        """
    else:
        account_join = ""

    if include_org_master and include_org_contact_matches:
        om_select = """
        , om.total_emails AS archive_org_total_emails
        , om.last_seen_at AS archive_org_last_seen
        , om.quote_email_count AS archive_org_quote_emails
        """
        om_join = "LEFT JOIN organization_master om ON om.domain = orgm.matched_domain"
    else:
        om_join = ""

    if include_contact_research:
        research_join = "LEFT JOIN lead_contact_research lcr ON lcr.lead_id = lm.id"
        research_select = """
        , lcr.contact_research_status AS contact_research_status
        , lcr.resolved_domain AS research_resolved_domain
        , lcr.resolved_contact_name AS research_resolved_contact_name
        , lcr.resolved_contact_email AS research_resolved_contact_email
        , lcr.contact_source AS research_contact_source
        , lcr.contact_research_notes AS research_contact_notes
        , lcr.updated_at AS contact_research_updated_at
        , lcr.updated_by AS contact_research_updated_by
        """

    return f"""
SELECT
  lm.id AS lead_id
  , lm.source_name
  , lm.source_record_id
  , lm.org_name
  , lm.contact_name
  , lm.email
  , lm.domain AS source_domain
  , lm.website AS source_website
  , lm.fit_bucket
  , lm.priority_score
  , lm.priority_reason
  , lm.status
  , lm.next_action
  , lm.review_owner
  , lm.last_reviewed_at
  , lm.evidence_summary
  , lm.notes
  , lm.buyer_kind
  , lm.region
  , lm.first_seen_at
  , lm.last_seen_at
  {archive_select}
  {account_select}
  {om_select}
  {research_select}
FROM lead_master lm
{org_join}
{contact_join}
{account_join}
{om_join}
{research_join}
WHERE {up}
"""


def fetch_leads_browse_df(
    conn: sqlite3.Connection,
    filters: LeadBrowseFilters | None = None,
) -> pd.DataFrame:
    """Return one row per upstream-active lead; empty if ``lead_master`` missing."""
    flt = filters or LeadBrowseFilters()
    ok, _ = lead_browse_ready(conn)
    if not ok:
        return pd.DataFrame()

    include_matches = _match_joins_available(conn)
    include_accounts = _account_joins_available(conn)
    include_om = include_matches and _table_exists(conn, "organization_master")
    include_research = _table_exists(conn, "lead_contact_research")

    sql = build_leads_browse_query(
        include_org_contact_matches=include_matches,
        include_org_master=include_om,
        include_lead_accounts=include_accounts,
        include_contact_research=include_research,
    )

    where_extra: list[str] = []
    params: list[object] = []

    if flt.fit_buckets:
        where_extra.append(f"lm.fit_bucket IN ({','.join('?' * len(flt.fit_buckets))})")
        params.extend(flt.fit_buckets)
    if flt.statuses:
        where_extra.append(f"lm.status IN ({','.join('?' * len(flt.statuses))})")
        params.extend(flt.statuses)
    if flt.sources:
        where_extra.append(f"lm.source_name IN ({','.join('?' * len(flt.sources))})")
        params.extend(flt.sources)

    if flt.needs_action_only:
        where_extra.append("(lm.next_action IS NULL OR TRIM(lm.next_action) = '')")

    am = _validate_archive_match(flt.archive_match)
    if include_matches:
        if am == "has":
            where_extra.append(
                "((orgm.matched_domain IS NOT NULL AND TRIM(orgm.matched_domain) != '') "
                "OR (lcm.matched_contact_email IS NOT NULL AND TRIM(lcm.matched_contact_email) != ''))"
            )
        elif am == "none":
            where_extra.append(
                "((orgm.matched_domain IS NULL OR TRIM(orgm.matched_domain) = '') "
                "AND (lcm.matched_contact_email IS NULL OR TRIM(lcm.matched_contact_email) = ''))"
            )

    if where_extra:
        sql = sql.strip() + " AND " + " AND ".join(where_extra)

    lim = max(50, min(int(flt.limit), 5000))
    sql += f"\nORDER BY (lm.priority_score IS NULL), lm.priority_score DESC, lm.id DESC\nLIMIT {lim}"

    try:
        return pd.read_sql_query(sql, conn, params=params)
    except (sqlite3.DatabaseError, PandasDatabaseError, ValueError):
        return pd.DataFrame()


def fetch_lead_account_rollups_df(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
) -> pd.DataFrame | None:
    """Account-level rollup table, or ``None`` if ``lead_account_master`` is absent."""
    if not _table_exists(conn, "lead_account_master"):
        return None
    cap = max(5, min(int(limit), 500))
    try:
        return pd.read_sql_query(
            f"""
            SELECT
              id AS account_id,
              canonical_name,
              primary_domain,
              lead_count,
              source_count,
              quality_status,
              region,
              last_seen_at,
              first_seen_at
            FROM lead_account_master
            ORDER BY lead_count DESC, id DESC
            LIMIT {cap}
            """,
            conn,
        )
    except (sqlite3.DatabaseError, ValueError):
        return None
