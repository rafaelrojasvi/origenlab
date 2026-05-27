"""SQLite schema for DeepSearch / Phase 10B prospect research (operator read model)."""

from __future__ import annotations

import sqlite3

LEAD_RESEARCH_DDL = """
CREATE TABLE IF NOT EXISTS lead_research_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_key TEXT NOT NULL UNIQUE,
  source_name TEXT NOT NULL,
  generated_at TEXT,
  input_file_name TEXT,
  row_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_research_prospect (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  prospect_key TEXT NOT NULL,
  organization_name TEXT NOT NULL,
  contact_name TEXT,
  email TEXT,
  domain TEXT,
  role_title TEXT,
  sector TEXT,
  region TEXT,
  buyer_type TEXT,
  likely_need TEXT,
  product_angle TEXT,
  evidence_url TEXT,
  evidence_note TEXT,
  source TEXT,
  input_priority_score INTEGER NOT NULL DEFAULT 0,
  final_score INTEGER NOT NULL DEFAULT 0,
  confidence TEXT,
  classification TEXT NOT NULL,
  spanish_message_angle TEXT,
  risk_flags TEXT,
  block_or_review_reason TEXT,
  recommended_next_action TEXT,
  status TEXT NOT NULL,
  campaign_bucket TEXT,
  is_blocked INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(batch_id, prospect_key),
  FOREIGN KEY(batch_id) REFERENCES lead_research_batch(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lead_research_prospect_batch ON lead_research_prospect(batch_id);
CREATE INDEX IF NOT EXISTS idx_lead_research_prospect_key ON lead_research_prospect(prospect_key);
CREATE INDEX IF NOT EXISTS idx_lead_research_prospect_classification ON lead_research_prospect(classification);
CREATE INDEX IF NOT EXISTS idx_lead_research_prospect_status ON lead_research_prospect(status);
CREATE INDEX IF NOT EXISTS idx_lead_research_prospect_score ON lead_research_prospect(final_score);

CREATE TABLE IF NOT EXISTS lead_research_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id INTEGER NOT NULL,
  evidence_kind TEXT NOT NULL DEFAULT 'public_url',
  evidence_url TEXT,
  evidence_note TEXT,
  source TEXT,
  confidence TEXT,
  FOREIGN KEY(prospect_id) REFERENCES lead_research_prospect(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lead_research_recommendation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id INTEGER NOT NULL,
  campaign_bucket TEXT,
  recommended_message_angle TEXT,
  recommended_next_action TEXT,
  why_this_lead TEXT,
  suggested_subject TEXT,
  suggested_body_preview TEXT,
  safety_note TEXT NOT NULL DEFAULT 'Revisión humana requerida. No enviar automáticamente.',
  FOREIGN KEY(prospect_id) REFERENCES lead_research_prospect(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lead_research_block_reason (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id INTEGER NOT NULL,
  reason_code TEXT NOT NULL,
  reason_label TEXT,
  FOREIGN KEY(prospect_id) REFERENCES lead_research_prospect(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lead_research_followup_candidate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  normalized_email TEXT NOT NULL,
  organization_name TEXT,
  domain TEXT,
  last_contacted_at TEXT,
  latest_subject_safe TEXT,
  recommended_follow_up_angle TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(batch_id) REFERENCES lead_research_batch(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lead_followup_batch ON lead_research_followup_candidate(batch_id);
"""


def ensure_lead_research_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(LEAD_RESEARCH_DDL)


def lead_research_tables_exist(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_research_prospect' LIMIT 1"
    ).fetchone()
    return bool(row)
