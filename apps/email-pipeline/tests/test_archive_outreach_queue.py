"""Archive outreach queue: schema, deterministic selection, and gate audit reasons."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.archive_outreach_queue import (
    ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
    ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO_FRESH_LAST_SEEN,
    ARCHIVE_CANDIDATE_SORT_LEGACY,
    ARCHIVE_OUTREACH_COLUMN_NAMES,
    LABDELIVERY_SIGNAL_PROVENANCE,
    audit_archive_outreach_candidates,
    fetch_archive_outreach_candidates,
    labdelivery_contact_last_seen,
)
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_DOMAIN_SUPPRESSION,
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


def test_audit_archive_candidates_operator_domain_suppression() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE emails (recipients TEXT, source_file TEXT, folder TEXT);
        CREATE TABLE contact_email_suppression (email TEXT PRIMARY KEY, suppression_reason_code TEXT);
        CREATE TABLE contact_domain_suppression (
          domain_norm TEXT PRIMARY KEY,
          suppression_reason_text TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE outreach_contact_state (contact_email_norm TEXT PRIMARY KEY, state TEXT);
        CREATE TABLE supplier_master (domain_norm TEXT);
        """
    )
    conn.execute("INSERT INTO contact_domain_suppression VALUES ('genesys.cl', 'block', 't', 't')")
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES (
          'claudio.toloza@genesys.cl','X','genesys.cl','Genesys','business',
          '2021-01-01','2025-01-02',20,20,0,0,0,0,0,0,0,'',0.5
        )
        """
    )
    conn.commit()

    audit = audit_archive_outreach_candidates(
        conn,
        gmail_user="contacto@origenlab.cl",
        limit=100,
        fetch_cap=100,
    )
    assert len(audit.rows) == 1
    row = audit.rows[0]
    assert row.candidate.contact_email == "claudio.toloza@genesys.cl"
    assert row.eligible is False
    assert row.reject_reason_code == REASON_DOMAIN_SUPPRESSION
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


def test_fetch_archive_candidates_company_intro_prefers_domain_over_hotter_gmail() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO organization_master (
          domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
          total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
        ) VALUES ('acme.cl','Acme','business','2021-01-01','2025-01-01',40,4,0,0,0,0,0,0,'','')
        """
    )
    conn.executescript(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('hot@gmail.com','Hot','gmail.com','','','2022-01-01','2025-01-02',100,80,20,0,0,0,0,0,0,'',1.0),
          ('low@acme.cl','Low','acme.cl','Acme','business','2022-01-01','2025-01-02',5,3,2,0,0,0,0,0,0,'',0.1);
        """
    )
    conn.commit()

    intro = fetch_archive_outreach_candidates(
        conn, fetch_cap=100, limit=10, archive_candidate_sort=ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO
    )
    assert [r.contact_email for r in intro] == ["low@acme.cl", "hot@gmail.com"]
    assert intro[0].warmth_score < intro[1].warmth_score

    legacy = fetch_archive_outreach_candidates(
        conn, fetch_cap=100, limit=10, archive_candidate_sort=ARCHIVE_CANDIDATE_SORT_LEGACY
    )
    assert [r.contact_email for r in legacy] == ["hot@gmail.com", "low@acme.cl"]

    conn.close()


def test_fetch_archive_candidates_company_intro_fresh_prefers_newer_last_seen() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO organization_master (
          domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
          total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
        ) VALUES ('acme.cl','Acme','business','2021-01-01','2025-01-01',40,4,0,0,0,0,0,0,'','')
        """
    )
    conn.executescript(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('old@acme.cl','Old','acme.cl','Acme','business','2022-01-01','2020-06-01',10,5,5,0,0,0,0,0,0,'',0.5),
          ('new@acme.cl','New','acme.cl','Acme','business','2022-01-01','2026-03-15',10,5,5,0,0,0,0,0,0,'',0.5);
        """
    )
    conn.commit()

    default_order = fetch_archive_outreach_candidates(
        conn, fetch_cap=100, limit=10, archive_candidate_sort=ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO
    )
    assert [r.contact_email for r in default_order] == ["old@acme.cl", "new@acme.cl"]

    fresh = fetch_archive_outreach_candidates(
        conn,
        fetch_cap=100,
        limit=10,
        archive_candidate_sort=ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO_FRESH_LAST_SEEN,
    )
    assert [r.contact_email for r in fresh] == ["new@acme.cl", "old@acme.cl"]
    conn.close()


def test_fetch_archive_candidates_company_intro_demotes_commercially_suppressed_contact() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE contact_candidate (
          contact_email TEXT PRIMARY KEY,
          org_domain TEXT,
          status TEXT NOT NULL DEFAULT 'new',
          suppression_flags TEXT NOT NULL DEFAULT '',
          rationale_text TEXT NOT NULL DEFAULT '',
          confidence_score REAL NOT NULL DEFAULT 0,
          strength_score REAL NOT NULL DEFAULT 0,
          evidence_count INTEGER NOT NULL DEFAULT 0,
          display_name TEXT,
          provenance_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO organization_master (
          domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
          total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
        ) VALUES ('acme.cl','Acme','business','2021-01-01','2025-01-01',80,8,0,0,0,0,0,0,'','');
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('ok@acme.cl','Ok','acme.cl','Acme','business','2022-01-01','2025-01-02',20,10,10,0,0,0,0,0,0,'',0.5),
          ('supp@gmail.com','Supp','gmail.com','','','2022-01-01','2025-01-02',90,50,40,0,0,0,0,0,0,'',0.9);
        INSERT INTO contact_candidate (
          contact_email, org_domain, status, suppression_flags, rationale_text,
          confidence_score, strength_score, evidence_count, created_at, updated_at
        ) VALUES
          ('ok@acme.cl', 'acme.cl', 'approved', '', 'ok', 0.5, 0.5, 1, 't', 't'),
          ('supp@gmail.com', 'gmail.com', 'suppressed', 'x', 'no', 0.5, 0.5, 1, 't', 't');
        """
    )
    conn.commit()

    rows = fetch_archive_outreach_candidates(
        conn, fetch_cap=100, limit=10, archive_candidate_sort=ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO
    )
    assert [r.contact_email for r in rows] == ["ok@acme.cl", "supp@gmail.com"]
    conn.close()


def test_labdelivery_contact_last_seen_matches_voice_sender_and_recipient() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recipients TEXT,
          sender TEXT,
          date_iso TEXT,
          date_raw TEXT,
          source_file TEXT,
          folder TEXT
        );
        INSERT INTO emails (recipients, sender, date_iso, date_raw, source_file, folder)
        VALUES (
          'Buyer <buyer@test.cl>, other@y.com',
          '"T" <ventas@labdelivery.cl>',
          '2025-06-15T10:00:00+00:00',
          '',
          'pst',
          'Sent'
        );
        """
    )
    conn.commit()
    m = labdelivery_contact_last_seen(
        conn, {"buyer@test.cl"}, voice_domains=frozenset({"labdelivery.cl"})
    )
    assert m.get("buyer@test.cl", "").startswith("2025-06-15")
    conn.close()


def test_fetch_archive_candidates_company_intro_labdelivery_before_same_domain_peer() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recipients TEXT,
          sender TEXT,
          date_iso TEXT,
          date_raw TEXT,
          source_file TEXT,
          folder TEXT
        );
        INSERT INTO organization_master (
          domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
          total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
        ) VALUES ('acme.cl','Acme','business','2021-01-01','2025-01-01',40,4,0,0,0,0,0,0,'','');
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES
          ('plain@acme.cl','Plain','acme.cl','Acme','business','2022-01-01','2025-01-02',80,40,40,0,0,0,0,0,0,'',0.9),
          ('touched@acme.cl','Touched','acme.cl','Acme','business','2022-01-01','2025-01-02',80,40,40,0,0,0,0,0,0,'',0.9);
        INSERT INTO emails (recipients, sender, date_iso, date_raw, source_file, folder) VALUES
          ('plain@acme.cl', '"T" <ventas@labdelivery.cl>', '2019-01-01T00:00:00+00:00', '', 'pst', 'Sent'),
          ('touched@acme.cl', '"T" <ventas@labdelivery.cl>', '2025-06-01T00:00:00+00:00', '', 'pst', 'Sent');
        """
    )
    conn.commit()
    rows = fetch_archive_outreach_candidates(
        conn, fetch_cap=100, limit=10, archive_candidate_sort=ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO
    )
    assert [r.contact_email for r in rows] == ["touched@acme.cl", "plain@acme.cl"]
    assert rows[0].last_contacted_by_labdelivery is True
    assert "2025-06-01" in rows[0].labdelivery_last_contact_at
    assert rows[0].labdelivery_signal_provenance == LABDELIVERY_SIGNAL_PROVENANCE
    assert rows[1].last_contacted_by_labdelivery is True
    assert "2019-01-01" in rows[1].labdelivery_last_contact_at
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

