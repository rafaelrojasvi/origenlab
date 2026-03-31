"""Supplier / sourcing layer (SQLite DDL). Separate from buyer ``lead_master``.

Tables hold DeepSearch workbook imports + manual review state. Canonical identity:
``supplier_master.domain_norm`` (one row per normalized domain).
"""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables

SUPPLIER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS supplier_import_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_filename TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  sheet_row_counts_json TEXT,
  category_priorities_json TEXT,
  resumen_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_supplier_import_batch_imported_at
  ON supplier_import_batch(imported_at DESC);

CREATE TABLE IF NOT EXISTS supplier_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_norm TEXT NOT NULL UNIQUE,
  trade_name TEXT,
  website TEXT,
  region_label TEXT,
  country_label TEXT,
  equipment_focus TEXT,
  notes TEXT,
  is_exclusion INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_supplier_master_exclusion ON supplier_master(is_exclusion);
CREATE INDEX IF NOT EXISTS idx_supplier_master_region ON supplier_master(region_label);

CREATE TABLE IF NOT EXISTS supplier_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER NOT NULL,
  batch_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  title TEXT,
  snippet TEXT,
  source_sheet TEXT,
  UNIQUE(supplier_id, url),
  FOREIGN KEY (supplier_id) REFERENCES supplier_master(id) ON DELETE CASCADE,
  FOREIGN KEY (batch_id) REFERENCES supplier_import_batch(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_supplier_evidence_supplier ON supplier_evidence(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_evidence_batch ON supplier_evidence(batch_id);

CREATE TABLE IF NOT EXISTS supplier_contact_channel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER NOT NULL,
  batch_id INTEGER NOT NULL,
  channel_type TEXT NOT NULL,
  value_raw TEXT NOT NULL,
  value_normalized TEXT NOT NULL DEFAULT '',
  is_preferred INTEGER NOT NULL DEFAULT 0,
  source_sheet TEXT,
  UNIQUE(supplier_id, channel_type, value_normalized),
  FOREIGN KEY (supplier_id) REFERENCES supplier_master(id) ON DELETE CASCADE,
  FOREIGN KEY (batch_id) REFERENCES supplier_import_batch(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_supplier_contact_supplier ON supplier_contact_channel(supplier_id);

CREATE TABLE IF NOT EXISTS supplier_priority_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  supplier_id INTEGER NOT NULL,
  batch_id INTEGER NOT NULL,
  tier TEXT NOT NULL,
  rank_in_list INTEGER,
  confidence_score REAL,
  confidence_label TEXT,
  category_context TEXT,
  UNIQUE(supplier_id, batch_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier_master(id) ON DELETE CASCADE,
  FOREIGN KEY (batch_id) REFERENCES supplier_import_batch(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_supplier_priority_tier ON supplier_priority_snapshot(tier);
CREATE INDEX IF NOT EXISTS idx_supplier_priority_batch ON supplier_priority_snapshot(batch_id);

CREATE TABLE IF NOT EXISTS supplier_review_state (
  supplier_id INTEGER PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'nuevo',
  review_owner TEXT,
  last_reviewed_at TEXT,
  next_action TEXT,
  internal_notes TEXT,
  FOREIGN KEY (supplier_id) REFERENCES supplier_master(id) ON DELETE CASCADE
);
"""


def ensure_supplier_tables(conn: sqlite3.Connection) -> None:
    """Create supplier tables if missing. Idempotent."""
    ensure_pipeline_meta_tables(conn)
    conn.executescript(SUPPLIER_SCHEMA_SQL)
    conn.commit()
