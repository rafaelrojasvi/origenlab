"""Commercial intelligence schema (v1).

This module keeps a strict separation between:
- Rebuildable facts/rollups derived from email history.
- Durable human-reviewed candidate state.
"""

from __future__ import annotations

import sqlite3

REBUILDABLE_SQL = """
CREATE TABLE IF NOT EXISTS commercial_email_signal_fact (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email_id INTEGER NOT NULL,
  source_file TEXT NOT NULL,
  sent_at TEXT,
  sender_email TEXT,
  sender_domain TEXT,
  contact_email TEXT,
  contact_domain TEXT,
  org_domain TEXT,
  signal_code TEXT NOT NULL,
  signal_kind TEXT NOT NULL,            -- positive | suppression
  reason_code TEXT NOT NULL,
  reason_text TEXT NOT NULL,
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  rationale_json TEXT NOT NULL,
  run_id INTEGER,
  created_at TEXT NOT NULL,
  UNIQUE(email_id, signal_code, reason_code, contact_email, org_domain),
  FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cisf_email_id ON commercial_email_signal_fact(email_id);
CREATE INDEX IF NOT EXISTS idx_cisf_org_domain ON commercial_email_signal_fact(org_domain);
CREATE INDEX IF NOT EXISTS idx_cisf_contact_email ON commercial_email_signal_fact(contact_email);
CREATE INDEX IF NOT EXISTS idx_cisf_signal_kind ON commercial_email_signal_fact(signal_kind);
CREATE INDEX IF NOT EXISTS idx_cisf_signal_code ON commercial_email_signal_fact(signal_code);

CREATE TABLE IF NOT EXISTS commercial_org_signal_rollup (
  org_domain TEXT PRIMARY KEY,
  first_seen_at TEXT,
  last_seen_at TEXT,
  evidence_email_count INTEGER NOT NULL,
  positive_signal_count INTEGER NOT NULL,
  suppression_signal_count INTEGER NOT NULL,
  suppression_reason_codes TEXT NOT NULL,
  positive_reason_codes TEXT NOT NULL,
  quote_signal_count INTEGER NOT NULL,
  procurement_signal_count INTEGER NOT NULL,
  technical_signal_count INTEGER NOT NULL,
  repeated_interaction_count INTEGER NOT NULL,
  invoice_or_payment_signal_count INTEGER NOT NULL,
  logistics_signal_count INTEGER NOT NULL,
  vendor_like_signal_count INTEGER NOT NULL,
  existing_client_signal_count INTEGER NOT NULL,
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  is_suppressed INTEGER NOT NULL,
  suppression_summary TEXT NOT NULL,
  run_id INTEGER,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ciosr_last_seen_at ON commercial_org_signal_rollup(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_ciosr_is_suppressed ON commercial_org_signal_rollup(is_suppressed);
CREATE INDEX IF NOT EXISTS idx_ciosr_confidence ON commercial_org_signal_rollup(confidence_score);

CREATE TABLE IF NOT EXISTS commercial_contact_signal_rollup (
  contact_email TEXT PRIMARY KEY,
  org_domain TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  evidence_email_count INTEGER NOT NULL,
  positive_signal_count INTEGER NOT NULL,
  suppression_signal_count INTEGER NOT NULL,
  suppression_reason_codes TEXT NOT NULL,
  positive_reason_codes TEXT NOT NULL,
  quote_signal_count INTEGER NOT NULL,
  procurement_signal_count INTEGER NOT NULL,
  technical_signal_count INTEGER NOT NULL,
  repeated_interaction_count INTEGER NOT NULL,
  invoice_or_payment_signal_count INTEGER NOT NULL,
  logistics_signal_count INTEGER NOT NULL,
  vendor_like_signal_count INTEGER NOT NULL,
  existing_client_signal_count INTEGER NOT NULL,
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  is_suppressed INTEGER NOT NULL,
  suppression_summary TEXT NOT NULL,
  run_id INTEGER,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cicsr_org_domain ON commercial_contact_signal_rollup(org_domain);
CREATE INDEX IF NOT EXISTS idx_cicsr_is_suppressed ON commercial_contact_signal_rollup(is_suppressed);

CREATE TABLE IF NOT EXISTS commercial_opportunity_fact (
  opportunity_key TEXT PRIMARY KEY,      -- org:<domain> (v1)
  org_domain TEXT NOT NULL,
  top_contact_email TEXT,
  top_signal_codes TEXT NOT NULL,
  evidence_email_count INTEGER NOT NULL,
  positive_signal_count INTEGER NOT NULL,
  suppression_signal_count INTEGER NOT NULL,
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  is_suppressed INTEGER NOT NULL,
  suppression_summary TEXT NOT NULL,
  rationale_json TEXT NOT NULL,
  run_id INTEGER,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ciof_org_domain ON commercial_opportunity_fact(org_domain);
CREATE INDEX IF NOT EXISTS idx_ciof_is_suppressed ON commercial_opportunity_fact(is_suppressed);
"""


DURABLE_SQL = """
CREATE TABLE IF NOT EXISTS organization_candidate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_domain TEXT NOT NULL UNIQUE,
  display_name TEXT,
  candidate_type TEXT NOT NULL DEFAULT 'net_new',
  status TEXT NOT NULL DEFAULT 'new',     -- new | needs_review | approved | rejected | suppressed | snoozed
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  evidence_count INTEGER NOT NULL,
  latest_activity_at TEXT,
  suppression_flags TEXT NOT NULL,
  rationale_text TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_org_candidate_status ON organization_candidate(status);
CREATE INDEX IF NOT EXISTS idx_org_candidate_confidence ON organization_candidate(confidence_score);

CREATE TABLE IF NOT EXISTS contact_candidate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_email TEXT NOT NULL UNIQUE,
  org_domain TEXT,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  evidence_count INTEGER NOT NULL,
  latest_activity_at TEXT,
  suppression_flags TEXT NOT NULL,
  rationale_text TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contact_candidate_org ON contact_candidate(org_domain);
CREATE INDEX IF NOT EXISTS idx_contact_candidate_status ON contact_candidate(status);

CREATE TABLE IF NOT EXISTS opportunity_candidate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_key TEXT NOT NULL UNIQUE,   -- org:<domain> (v1)
  org_domain TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  confidence_score REAL NOT NULL,
  strength_score REAL NOT NULL,
  evidence_count INTEGER NOT NULL,
  latest_activity_at TEXT,
  suppression_flags TEXT NOT NULL,
  rationale_text TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunity_candidate_org ON opportunity_candidate(org_domain);
CREATE INDEX IF NOT EXISTS idx_opportunity_candidate_status ON opportunity_candidate(status);

CREATE TABLE IF NOT EXISTS candidate_review_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_kind TEXT NOT NULL,              -- organization | contact | opportunity
  entity_key TEXT NOT NULL,
  previous_status TEXT,
  next_status TEXT NOT NULL,
  reason_code TEXT,
  reason_text TEXT,
  note_text TEXT,
  actor TEXT NOT NULL DEFAULT 'system',
  run_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidate_review_entity ON candidate_review_event(entity_kind, entity_key);
CREATE INDEX IF NOT EXISTS idx_candidate_review_created ON candidate_review_event(created_at);

CREATE TABLE IF NOT EXISTS candidate_manual_override (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_kind TEXT NOT NULL,              -- organization | contact | opportunity
  entity_key TEXT NOT NULL,
  override_code TEXT NOT NULL,            -- force_status | force_suppress | unsuppress
  override_value TEXT NOT NULL,
  reason_text TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT 'human',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(entity_kind, entity_key, override_code, is_active)
);
CREATE INDEX IF NOT EXISTS idx_candidate_override_entity ON candidate_manual_override(entity_kind, entity_key);
"""


VIEW_SQL = """
DROP VIEW IF EXISTS v_commercial_candidate_queue;
CREATE VIEW v_commercial_candidate_queue AS
SELECT
  'organization' AS entity_kind,
  org_domain AS entity_key,
  org_domain AS org_domain,
  COALESCE(display_name, org_domain) AS display_name,
  candidate_type,
  status,
  confidence_score,
  strength_score,
  evidence_count,
  latest_activity_at,
  suppression_flags,
  rationale_text,
  TRIM(
    CASE WHEN COALESCE(suppression_flags, '') != ''
      THEN rationale_text || ' | Suppression flags: ' || suppression_flags
      ELSE rationale_text END
  ) AS reason_summary,
  updated_at
FROM organization_candidate
UNION ALL
SELECT
  'contact' AS entity_kind,
  contact_email AS entity_key,
  org_domain,
  COALESCE(display_name, contact_email) AS display_name,
  NULL AS candidate_type,
  status,
  confidence_score,
  strength_score,
  evidence_count,
  latest_activity_at,
  suppression_flags,
  rationale_text,
  TRIM(
    CASE WHEN COALESCE(suppression_flags, '') != ''
      THEN rationale_text || ' | Suppression flags: ' || suppression_flags
      ELSE rationale_text END
  ) AS reason_summary,
  updated_at
FROM contact_candidate
UNION ALL
SELECT
  'opportunity' AS entity_kind,
  opportunity_key AS entity_key,
  org_domain,
  opportunity_key AS display_name,
  NULL AS candidate_type,
  status,
  confidence_score,
  strength_score,
  evidence_count,
  latest_activity_at,
  suppression_flags,
  rationale_text,
  TRIM(
    CASE WHEN COALESCE(suppression_flags, '') != ''
      THEN rationale_text || ' | Suppression flags: ' || suppression_flags
      ELSE rationale_text END
  ) AS reason_summary,
  updated_at
FROM opportunity_candidate
;
"""


def ensure_commercial_intel_tables(conn: sqlite3.Connection) -> None:
    """Create commercial intelligence tables and queue view (idempotent)."""
    conn.executescript(REBUILDABLE_SQL)
    conn.executescript(DURABLE_SQL)
    conn.executescript(VIEW_SQL)
    conn.commit()

