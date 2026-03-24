"""Lead pipeline schema. Tables are created by the leads pipeline, not by db.init_schema."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.bi_views import refresh_lead_match_summary_view
from origenlab_email_pipeline.lead_identity_norm import compute_lead_norm_fields
from origenlab_email_pipeline.lead_master_keys import (
    backfill_canonical_source_record_ids,
    count_duplicate_key_groups,
    ensure_lead_master_source_unique_index,
)
from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables

LEAD_SCHEMA_SQL = """
-- Raw records from external sources (idempotent re-fetch).
CREATE TABLE IF NOT EXISTS external_leads_raw (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  raw_json TEXT,
  source_url TEXT,
  UNIQUE(source_name, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_external_leads_raw_source ON external_leads_raw(source_name, source_record_id);
CREATE INDEX IF NOT EXISTS idx_external_leads_raw_fetched ON external_leads_raw(source_name, fetched_at);

-- Normalized leads for prospecting.
CREATE TABLE IF NOT EXISTS lead_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  source_type TEXT,
  source_record_id TEXT,
  source_url TEXT,
  org_name TEXT,
  contact_name TEXT,
  email TEXT,
  phone TEXT,
  website TEXT,
  domain TEXT,
  region TEXT,
  city TEXT,
  lead_type TEXT,
  organization_type_guess TEXT,
  buyer_kind TEXT,
  equipment_match_tags TEXT,
  lab_context_score REAL,
  lab_context_tags TEXT,
  evidence_summary TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  priority_score REAL,
  priority_reason TEXT,
  fit_bucket TEXT,
  status TEXT DEFAULT 'nuevo',
  review_owner TEXT,
  last_reviewed_at TEXT,
  next_action TEXT,
  notes TEXT,
  email_norm TEXT,
  domain_norm TEXT,
  org_name_norm TEXT,
  upstream_sync_state TEXT DEFAULT 'active',
  upstream_retired_at TEXT,
  upstream_retired_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_lead_master_source ON lead_master(source_name);
CREATE INDEX IF NOT EXISTS idx_lead_master_domain ON lead_master(domain);
CREATE INDEX IF NOT EXISTS idx_lead_master_status ON lead_master(status);
CREATE INDEX IF NOT EXISTS idx_lead_master_priority ON lead_master(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_lead_master_last_seen ON lead_master(last_seen_at);
-- Norm + org-match run indexes are created after ALTER migrations (older DBs may lack columns).

-- Matching to existing organization_master (read-only from mart).
CREATE TABLE IF NOT EXISTS lead_matches_existing_orgs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  matched_domain TEXT NOT NULL,
  matched_org_name TEXT,
  match_type TEXT NOT NULL,
  confidence_score REAL NOT NULL,
  already_in_archive_flag INTEGER NOT NULL DEFAULT 1,
  pipeline_run_id INTEGER,
  evidence_json TEXT,
  FOREIGN KEY(lead_id) REFERENCES lead_master(id) ON DELETE CASCADE,
  FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_run(id)
);
CREATE INDEX IF NOT EXISTS idx_lead_matches_lead_id ON lead_matches_existing_orgs(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_matches_domain ON lead_matches_existing_orgs(matched_domain);
-- pipeline_run_id index: created post-migration for DBs that predate Phase 1.

-- Matching to contact_master (email / domain+name heuristics).
CREATE TABLE IF NOT EXISTS lead_matches_existing_contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  matched_contact_email TEXT NOT NULL,
  matched_contact_name TEXT,
  matched_domain TEXT,
  match_type TEXT NOT NULL,
  confidence_score REAL NOT NULL,
  already_in_archive_flag INTEGER NOT NULL DEFAULT 1,
  evidence_json TEXT,
  pipeline_run_id INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY(lead_id) REFERENCES lead_master(id) ON DELETE CASCADE,
  FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_run(id)
);
CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_lead_id ON lead_matches_existing_contacts(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_email ON lead_matches_existing_contacts(matched_contact_email);
CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_domain ON lead_matches_existing_contacts(matched_domain);
CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_pipeline_run ON lead_matches_existing_contacts(pipeline_run_id);

-- Manual / Deep Research contact-hunt data (v1.2+). Not modified by normalize_leads.
CREATE TABLE IF NOT EXISTS lead_outreach_enrichment (
  lead_id INTEGER PRIMARY KEY,
  enrichment_json TEXT NOT NULL,
  source_file TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(lead_id) REFERENCES lead_master(id) ON DELETE CASCADE
);

-- Audit trail for upstream raw vs lead_master reconciliation (dry-run and apply).
CREATE TABLE IF NOT EXISTS lead_upstream_reconcile_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at TEXT NOT NULL,
  dry_run INTEGER NOT NULL,
  lead_id INTEGER NOT NULL,
  source_name TEXT NOT NULL,
  canonical_source_record_id TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT,
  FOREIGN KEY(lead_id) REFERENCES lead_master(id)
);
CREATE INDEX IF NOT EXISTS idx_lead_upstream_reconcile_log_run ON lead_upstream_reconcile_log(run_at);
CREATE INDEX IF NOT EXISTS idx_lead_upstream_reconcile_log_lead ON lead_upstream_reconcile_log(lead_id);
"""


def _migrate_lead_matches_org_columns(conn: sqlite3.Connection) -> None:
    """Add pipeline_run_id and evidence_json to existing lead_matches_existing_orgs."""
    for col in ("pipeline_run_id INTEGER", "evidence_json TEXT"):
        try:
            conn.execute(f"ALTER TABLE lead_matches_existing_orgs ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _migrate_lead_master_norm_columns(conn: sqlite3.Connection) -> None:
    for col in ("email_norm TEXT", "domain_norm TEXT", "org_name_norm TEXT"):
        try:
            conn.execute(f"ALTER TABLE lead_master ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def backfill_lead_master_norm_columns(conn: sqlite3.Connection) -> int:
    """Populate email_norm, domain_norm, org_name_norm where NULL or empty. Returns rows updated."""
    ensure_pipeline_meta_tables(conn)
    _migrate_lead_master_norm_columns(conn)
    rows = conn.execute(
        """
        SELECT id, email, domain, org_name FROM lead_master
        WHERE email_norm IS NULL OR email_norm = ''
           OR domain_norm IS NULL OR domain_norm = ''
           OR org_name_norm IS NULL OR org_name_norm = ''
        """
    ).fetchall()
    n = 0
    for lead_id, email, domain, org_name in rows:
        norms = compute_lead_norm_fields(email, domain, org_name)
        conn.execute(
            """
            UPDATE lead_master SET email_norm = ?, domain_norm = ?, org_name_norm = ?
            WHERE id = ?
            """,
            (
                norms["email_norm"],
                norms["domain_norm"],
                norms["org_name_norm"],
                lead_id,
            ),
        )
        n += 1
    conn.commit()
    return n


def ensure_leads_tables_ddl_base(conn: sqlite3.Connection) -> None:
    """Create/migrate lead tables and secondary indexes (no canonical key backfill, no UNIQUE index)."""
    ensure_pipeline_meta_tables(conn)
    conn.executescript(LEAD_SCHEMA_SQL)
    # Existing DBs created before Phase 1 hardening.
    _migrate_lead_master_norm_columns(conn)
    _migrate_lead_matches_org_columns(conn)
    # Additive migrations for v1 refinements (safe on older DBs).
    for col in (
        "buyer_kind TEXT",
        "lab_context_score REAL",
        "lab_context_tags TEXT",
        "fit_bucket TEXT",
        "upstream_sync_state TEXT DEFAULT 'active'",
        "upstream_retired_at TEXT",
        "upstream_retired_reason TEXT",
    ):
        try:
            conn.execute(f"ALTER TABLE lead_master ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute(
            """
            UPDATE lead_master
            SET upstream_sync_state = 'active'
            WHERE upstream_sync_state IS NULL OR TRIM(upstream_sync_state) = ''
            """
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    # Indexes (IF NOT EXISTS in LEAD_SCHEMA_SQL for new installs; create missing on old DBs).
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_lead_master_email_norm ON lead_master(email_norm)",
        "CREATE INDEX IF NOT EXISTS idx_lead_master_domain_norm ON lead_master(domain_norm)",
        "CREATE INDEX IF NOT EXISTS idx_lead_master_org_name_norm ON lead_master(org_name_norm)",
        "CREATE INDEX IF NOT EXISTS idx_lead_matches_org_pipeline_run ON lead_matches_existing_orgs(pipeline_run_id)",
        "CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_lead_id ON lead_matches_existing_contacts(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_email ON lead_matches_existing_contacts(matched_contact_email)",
        "CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_domain ON lead_matches_existing_contacts(matched_domain)",
        "CREATE INDEX IF NOT EXISTS idx_lead_matches_contacts_pipeline_run ON lead_matches_existing_contacts(pipeline_run_id)",
    ):
        try:
            conn.execute(stmt)
            conn.commit()
        except sqlite3.OperationalError:
            pass


def finalize_lead_master_source_keys(conn: sqlite3.Connection) -> None:
    """Canonicalize source_record_id values and enforce UNIQUE(source_name, source_record_id).

    Drops the unique index first so backfill can collapse whitespace/NULL keys without
    violating the constraint mid-UPDATE. If duplicates remain, raises RuntimeError (run dedupe).
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_master'"
    ).fetchone():
        conn.commit()
        return
    conn.execute("DROP INDEX IF EXISTS uidx_lead_master_source_name_record")
    conn.commit()
    backfill_canonical_source_record_ids(conn)
    if count_duplicate_key_groups(conn) > 0:
        raise RuntimeError(
            "lead_master has duplicate (source_name, source_record_id) after canonical "
            "backfill. Run:\n"
            "  uv run python scripts/leads/audit_lead_master_duplicates.py\n"
            "  uv run python scripts/leads/dedupe_lead_master.py --apply"
        )
    ensure_lead_master_source_unique_index(conn)
    conn.commit()


def ensure_leads_tables_ddl(conn: sqlite3.Connection) -> None:
    """Create/migrate lead tables and indexes; then canonical keys + UNIQUE index on lead_master."""
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)


def ensure_leads_tables(
    conn: sqlite3.Connection,
    *,
    backfill_norms: bool = True,
    refresh_view: bool = True,
) -> None:
    """Create lead tables if they do not exist. Idempotent.

    Defaults preserve legacy behavior: DDL, then norm backfill, then BI view refresh.
    """
    ensure_leads_tables_ddl(conn)
    if backfill_norms:
        backfill_lead_master_norm_columns(conn)
    if refresh_view:
        refresh_lead_match_summary_view(conn)
