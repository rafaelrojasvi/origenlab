"""Durable SQLite tables for confirmed purchase orders / buyer events."""

from __future__ import annotations

import sqlite3

COMMERCIAL_PURCHASE_DDL = """
CREATE TABLE IF NOT EXISTS commercial_purchase_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_email_id INTEGER,
  source_message_id TEXT,
  source_file TEXT,
  email_subject TEXT,
  email_from TEXT,
  email_to TEXT,
  email_date_iso TEXT,
  buyer_org_name TEXT NOT NULL,
  buyer_rut TEXT,
  buyer_contact_name TEXT,
  buyer_contact_role TEXT,
  buyer_contact_email TEXT,
  buyer_domain TEXT,
  purchase_status TEXT NOT NULL,
  oc_number TEXT NOT NULL,
  oc_date TEXT,
  quote_number TEXT,
  quote_date TEXT,
  project_name TEXT,
  project_code TEXT,
  project_responsible TEXT,
  associated_line TEXT,
  net_amount_clp INTEGER,
  iva_amount_clp INTEGER,
  gross_amount_clp INTEGER,
  currency TEXT NOT NULL DEFAULT 'CLP',
  payment_terms TEXT,
  delivery_address TEXT,
  invoice_email TEXT,
  invoice_cc_email TEXT,
  dispatch_requested INTEGER NOT NULL DEFAULT 0,
  invoice_requested INTEGER NOT NULL DEFAULT 0,
  bank_details_requested INTEGER NOT NULL DEFAULT 0,
  commercial_summary TEXT,
  confidence TEXT NOT NULL DEFAULT 'operator_confirmed',
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(source_email_id) REFERENCES emails(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_commercial_purchase_events_email_oc
  ON commercial_purchase_events(source_email_id, oc_number)
  WHERE source_email_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_commercial_purchase_events_buyer_oc
  ON commercial_purchase_events(buyer_org_name, oc_number);
CREATE INDEX IF NOT EXISTS idx_commercial_purchase_events_oc_number
  ON commercial_purchase_events(oc_number);
CREATE INDEX IF NOT EXISTS idx_commercial_purchase_events_email_date
  ON commercial_purchase_events(email_date_iso DESC);

CREATE TABLE IF NOT EXISTS commercial_purchase_event_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_event_id INTEGER NOT NULL,
  line_number INTEGER NOT NULL,
  ref_code TEXT,
  product_name TEXT NOT NULL,
  brand TEXT,
  quantity TEXT,
  net_amount_clp INTEGER,
  evidence_source TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(purchase_event_id) REFERENCES commercial_purchase_events(id) ON DELETE CASCADE,
  UNIQUE(purchase_event_id, line_number)
);
CREATE INDEX IF NOT EXISTS idx_commercial_purchase_event_items_event
  ON commercial_purchase_event_items(purchase_event_id);

CREATE TABLE IF NOT EXISTS commercial_purchase_event_attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_event_id INTEGER NOT NULL,
  source_attachment_id INTEGER,
  filename TEXT NOT NULL,
  mime_type TEXT,
  document_type TEXT,
  extracted_text_present INTEGER NOT NULL DEFAULT 0,
  extracted_amounts_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(purchase_event_id) REFERENCES commercial_purchase_events(id) ON DELETE CASCADE,
  FOREIGN KEY(source_attachment_id) REFERENCES attachments(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_commercial_purchase_event_attachments_event
  ON commercial_purchase_event_attachments(purchase_event_id);
"""


def ensure_commercial_purchase_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(COMMERCIAL_PURCHASE_DDL)
    conn.commit()


def commercial_purchase_tables_exist(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='commercial_purchase_events'
        LIMIT 1
        """
    ).fetchone()
    return bool(row)
