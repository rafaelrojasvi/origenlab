"""Archive outreach queue: schema, deterministic selection, and gate audit reasons."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.archive_outreach_queue import (
    ARCHIVE_OUTREACH_COLUMN_NAMES,
    audit_archive_outreach_candidates,
    fetch_archive_outreach_candidates,
)
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_OUTREACH_CONTACTED,
    REASON_SENT_HISTORY,
    REASON_SUPPLIER_DOMAIN,
    REASON_SUPPRESSION,
)


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE contact_master (
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
        CREATE TABLE organization_master (
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
        CREATE TABLE opportunity_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          email_id INTEGER,
          attachment_id INTEGER,
          score REAL,
          details_json TEXT,
          created_at TEXT
        );
        """
    )


def test_fetch_archive_candidates_schema_and_sorting() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO organization_master (
          domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
          total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
        ) VALUES ('uni.cl','Universidad','education','2021-01-01','2025-01-01',120,12,7,2,1,0,0,0,'','')
        """
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('first@uni.cl','First','uni.cl','Universidad','education','2022-01-01','2025-01-02',30,20,10,2,0,0,0,0,0,'',0.90),
          ('second@gmail.com','Second','gmail.com','Universidad','education','2021-01-01','2024-01-02',10,8,2,0,0,0,0,0,0,'',0.40),
          ('bad-no-at','Bad','uni.cl','Universidad','education','2021-01-01','2024-01-02',99,8,2,0,0,0,0,0,0,'',0.99)
        """
    )
    conn.execute(
        "INSERT INTO opportunity_signals (signal_type, entity_kind, entity_key, score) VALUES ('dormant_contact','contact','first@uni.cl',9.0)"
    )
    conn.commit()

    rows = fetch_archive_outreach_candidates(conn, fetch_cap=100, limit=10)
    assert len(rows) == 2
    assert rows[0].contact_email == "first@uni.cl"
    assert rows[0].warmth_score >= rows[1].warmth_score
    assert rows[0].dormant_signal_count >= 1
    assert rows[0].warmth_band in {"strong", "medium", "weak"}
    assert isinstance(rows[0].quality_flags, str) and "warmth_" in rows[0].quality_flags
    assert rows[1].is_free_personal_domain is True
    assert tuple(rows[0].to_dict().keys()) == ARCHIVE_OUTREACH_COLUMN_NAMES
    conn.close()


def test_audit_archive_candidates_gate_reasons_parity() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE emails (recipients TEXT, source_file TEXT, folder TEXT);
        CREATE TABLE contact_email_suppression (email TEXT PRIMARY KEY, suppression_reason_code TEXT);
        CREATE TABLE outreach_contact_state (contact_email_norm TEXT PRIMARY KEY, state TEXT);
        CREATE TABLE supplier_master (domain_norm TEXT);
        """
    )
    conn.execute(
        "INSERT INTO emails VALUES ('sent@x.cl', 'gmail:contacto@origenlab.cl/1', '[Gmail]/Enviados')"
    )
    conn.execute("INSERT INTO contact_email_suppression VALUES ('supp@x.cl', 'manual_do_not_contact')")
    conn.execute("INSERT INTO outreach_contact_state VALUES ('contacted@x.cl', 'contacted')")
    conn.execute("INSERT INTO supplier_master VALUES ('supplier.cl')")
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('ok@x.cl','Ok','x.cl','Org X','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.5),
          ('sent@x.cl','Sent','x.cl','Org X','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.5),
          ('supp@x.cl','Supp','x.cl','Org X','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.5),
          ('contacted@x.cl','Contacted','x.cl','Org X','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.5),
          ('buyer@supplier.cl','Supplier','supplier.cl','Supplier Org','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.5)
        """
    )
    conn.commit()

    audit = audit_archive_outreach_candidates(
        conn,
        gmail_user="contacto@origenlab.cl",
        limit=100,
        fetch_cap=100,
    )
    by_email = {r.candidate.contact_email: r for r in audit.rows}
    assert by_email["ok@x.cl"].eligible is True
    assert by_email["sent@x.cl"].reject_reason_code == REASON_SENT_HISTORY
    assert by_email["supp@x.cl"].reject_reason_code == REASON_SUPPRESSION
    assert by_email["contacted@x.cl"].reject_reason_code == REASON_OUTREACH_CONTACTED
    assert by_email["buyer@supplier.cl"].reject_reason_code == REASON_SUPPLIER_DOMAIN
    assert audit.blocked_by_reason[REASON_SENT_HISTORY] == 1
    assert audit.blocked_by_reason[REASON_SUPPRESSION] == 1
    assert audit.blocked_by_reason[REASON_OUTREACH_CONTACTED] == 1
    assert audit.blocked_by_reason[REASON_SUPPLIER_DOMAIN] == 1
    conn.close()


def test_archive_quality_flags_supplier_marketplace_and_generic_local() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE supplier_master (domain_norm TEXT);
        INSERT INTO supplier_master VALUES ('supplier.cl');
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('info@supplier.cl','Info','supplier.cl','Supplier Org','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.7),
          ('contacto@mercadopublico.cl','Mp','mercadopublico.cl','Marketplace','business','2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.7);
        """
    )
    conn.commit()
    rows = fetch_archive_outreach_candidates(conn, fetch_cap=100, limit=10)
    by = {r.contact_email: r for r in rows}
    assert by["info@supplier.cl"].is_supplier_like is True
    assert by["info@supplier.cl"].is_generic_mailbox_localpart is True
    assert by["contacto@mercadopublico.cl"].is_marketplace_like is True
    assert by["contacto@mercadopublico.cl"].is_admin_transactional_like is True
    conn.close()

