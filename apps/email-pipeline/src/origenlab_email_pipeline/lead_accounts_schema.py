"""Lead account rollup layer (additive). Does not modify lead_master or external_leads_raw.

organization_master uses domain TEXT as PRIMARY KEY (no integer id). Matches use organization_domain.
"""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.bi_views import refresh_lead_match_summary_view
from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables

LEAD_ACCOUNT_SCHEMA_SQL = """
-- CRM-style account rollup over lead_master (one account -> many tenders/leads).
CREATE TABLE IF NOT EXISTS lead_account_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_dedupe_key TEXT NOT NULL UNIQUE,
  canonical_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  primary_domain TEXT,
  official_website TEXT,
  org_type TEXT,
  region TEXT,
  city TEXT,
  country TEXT NOT NULL DEFAULT 'CL',
  source_count INTEGER NOT NULL DEFAULT 0,
  lead_count INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT,
  last_seen_at TEXT,
  quality_status TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lead_account_master_normalized_name
  ON lead_account_master(normalized_name);
CREATE INDEX IF NOT EXISTS idx_lead_account_master_primary_domain
  ON lead_account_master(primary_domain);
CREATE INDEX IF NOT EXISTS idx_lead_account_master_quality
  ON lead_account_master(quality_status);
CREATE INDEX IF NOT EXISTS idx_lead_account_master_lead_count
  ON lead_account_master(lead_count DESC);

CREATE TABLE IF NOT EXISTS lead_account_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_account_id INTEGER NOT NULL,
  alias_name TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  alias_type TEXT,
  source_name TEXT,
  confidence REAL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(lead_account_id) REFERENCES lead_account_master(id) ON DELETE CASCADE,
  UNIQUE(lead_account_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_lead_account_aliases_account
  ON lead_account_aliases(lead_account_id);
CREATE INDEX IF NOT EXISTS idx_lead_account_aliases_normalized_alias
  ON lead_account_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS lead_account_membership (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  lead_account_id INTEGER NOT NULL,
  membership_method TEXT NOT NULL,
  confidence REAL NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 1,
  evidence_json TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(lead_id, lead_account_id),
  FOREIGN KEY(lead_id) REFERENCES lead_master(id) ON DELETE CASCADE,
  FOREIGN KEY(lead_account_id) REFERENCES lead_account_master(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lead_account_membership_lead_id
  ON lead_account_membership(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_account_membership_account_id
  ON lead_account_membership(lead_account_id);

-- organization_master PK is domain (TEXT). We store organization_domain, not a numeric id.
CREATE TABLE IF NOT EXISTS lead_account_matches_existing_orgs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_account_id INTEGER NOT NULL,
  organization_domain TEXT NOT NULL,
  match_method TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence_json TEXT,
  review_status TEXT NOT NULL DEFAULT 'auto',
  created_at TEXT NOT NULL,
  pipeline_run_id INTEGER,
  UNIQUE(lead_account_id, organization_domain),
  FOREIGN KEY(lead_account_id) REFERENCES lead_account_master(id) ON DELETE CASCADE,
  FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_run(id)
);
-- organization_domain should match organization_master.domain when mart exists (no FK: mart may be empty).

CREATE INDEX IF NOT EXISTS idx_lead_account_matches_account
  ON lead_account_matches_existing_orgs(lead_account_id);
CREATE INDEX IF NOT EXISTS idx_lead_account_matches_org_domain
  ON lead_account_matches_existing_orgs(organization_domain);
-- pipeline_run_id index: created after ALTER migration (older DBs lack the column).

CREATE TABLE IF NOT EXISTS lead_account_overrides (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  override_type TEXT NOT NULL,
  source_value TEXT,
  normalized_source_value TEXT,
  target_account_name TEXT,
  target_account_id INTEGER,
  notes TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lead_account_overrides_normalized
  ON lead_account_overrides(normalized_source_value)
  WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_lead_account_overrides_type
  ON lead_account_overrides(override_type, is_active);
"""


def ensure_lead_account_tables(conn: sqlite3.Connection) -> None:
    """Create lead account rollup tables if missing. Idempotent."""
    ensure_pipeline_meta_tables(conn)
    conn.executescript(LEAD_ACCOUNT_SCHEMA_SQL)
    try:
        conn.execute("ALTER TABLE lead_account_matches_existing_orgs ADD COLUMN pipeline_run_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lead_account_matches_pipeline_run ON lead_account_matches_existing_orgs(pipeline_run_id)"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()
    refresh_lead_match_summary_view(conn)
