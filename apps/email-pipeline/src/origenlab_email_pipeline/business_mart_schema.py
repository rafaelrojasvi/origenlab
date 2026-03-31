"""Business mart schema (client-facing derived layer).

Raw archive tables remain untouched:
- emails
- attachments
- attachment_extracts

This module defines additive, rebuildable materialized tables:
- contact_master
- organization_master
- document_master
- opportunity_signals
"""

from __future__ import annotations

BUSINESS_MART_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contact_master (
  email TEXT PRIMARY KEY,
  contact_name_best TEXT,
  domain TEXT,
  organization_name_guess TEXT,
  organization_type_guess TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  total_emails INTEGER,
  inbound_emails INTEGER,
  outbound_emails INTEGER,
  quote_email_count INTEGER,
  invoice_email_count INTEGER,
  purchase_email_count INTEGER,
  business_doc_email_count INTEGER,
  quote_doc_count INTEGER,
  invoice_doc_count INTEGER,
  top_equipment_tags TEXT,
  confidence_score REAL
);

CREATE INDEX IF NOT EXISTS idx_contact_master_domain ON contact_master(domain);
CREATE INDEX IF NOT EXISTS idx_contact_master_last_seen ON contact_master(last_seen_at);

CREATE TABLE IF NOT EXISTS organization_master (
  domain TEXT PRIMARY KEY,
  organization_name_guess TEXT,
  organization_type_guess TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  total_emails INTEGER,
  total_contacts INTEGER,
  quote_email_count INTEGER,
  invoice_email_count INTEGER,
  purchase_email_count INTEGER,
  business_doc_email_count INTEGER,
  quote_doc_count INTEGER,
  invoice_doc_count INTEGER,
  top_equipment_tags TEXT,
  key_contacts TEXT
);

CREATE INDEX IF NOT EXISTS idx_org_master_last_seen ON organization_master(last_seen_at);

CREATE TABLE IF NOT EXISTS document_master (
  attachment_id INTEGER PRIMARY KEY,
  email_id INTEGER,
  filename TEXT,
  extension TEXT,
  sender_email TEXT,
  sender_domain TEXT,
  recipient_domain TEXT,
  sent_at TEXT,
  doc_type TEXT,
  extracted_preview_raw TEXT,
  extracted_preview_clean TEXT,
  preview_quality_score REAL,
  has_quote_terms INTEGER,
  has_invoice_terms INTEGER,
  has_purchase_terms INTEGER,
  has_price_list_terms INTEGER,
  equipment_tags TEXT,
  FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_master_sender_domain ON document_master(sender_domain);
CREATE INDEX IF NOT EXISTS idx_document_master_recipient_domain ON document_master(recipient_domain);
CREATE INDEX IF NOT EXISTS idx_document_master_sent_at ON document_master(sent_at);
CREATE INDEX IF NOT EXISTS idx_document_master_doc_type ON document_master(doc_type);

CREATE TABLE IF NOT EXISTS opportunity_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_type TEXT NOT NULL,
  entity_kind TEXT NOT NULL,         -- 'contact' | 'organization'
  entity_key TEXT NOT NULL,          -- contact email or org domain
  email_id INTEGER,
  attachment_id INTEGER,
  score REAL,
  details_json TEXT,
  created_at TEXT                    -- mart rebuild stamp (UTC/Z), not email / business event time
);

CREATE INDEX IF NOT EXISTS idx_opportunity_signals_entity ON opportunity_signals(entity_kind, entity_key);
CREATE INDEX IF NOT EXISTS idx_opportunity_signals_type ON opportunity_signals(signal_type);
"""

