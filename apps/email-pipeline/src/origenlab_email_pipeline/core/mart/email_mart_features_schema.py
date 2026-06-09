"""SQLite schema for precomputed per-email mart features (additive, rebuildable)."""

from __future__ import annotations

import sqlite3

EMAIL_MART_FEATURES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS email_mart_features (
  email_id INTEGER PRIMARY KEY,
  message_id TEXT,
  source_file TEXT,
  folder TEXT,
  sender_email TEXT,
  sender_domain TEXT,
  recipient_emails_json TEXT NOT NULL DEFAULT '[]',
  external_targets_json TEXT NOT NULL DEFAULT '[]',
  direction TEXT NOT NULL DEFAULT 'other',
  is_noise INTEGER NOT NULL DEFAULT 0,
  is_quote_email INTEGER NOT NULL DEFAULT 0,
  is_invoice_email INTEGER NOT NULL DEFAULT 0,
  is_purchase_email INTEGER NOT NULL DEFAULT 0,
  equipment_tags_json TEXT NOT NULL DEFAULT '[]',
  mart_date_iso TEXT,
  body_len INTEGER NOT NULL DEFAULT 0,
  feature_source_hash TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_mart_features_sender_domain
  ON email_mart_features(sender_domain);
CREATE INDEX IF NOT EXISTS idx_email_mart_features_direction
  ON email_mart_features(direction);
CREATE INDEX IF NOT EXISTS idx_email_mart_features_is_noise
  ON email_mart_features(is_noise);
"""


def ensure_email_mart_features_table(conn: sqlite3.Connection) -> None:
    """Create ``email_mart_features`` and indexes (idempotent)."""
    conn.executescript(EMAIL_MART_FEATURES_SCHEMA_SQL)
    conn.commit()
