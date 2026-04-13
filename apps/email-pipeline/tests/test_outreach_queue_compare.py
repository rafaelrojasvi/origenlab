from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.outreach_queue_compare import (
    SOURCE_LABEL_ARCHIVE,
    SOURCE_LABEL_LEAD,
    compare_archive_vs_lead_outreach,
)


def _seed_common(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE contact_master (
          email TEXT PRIMARY KEY,
          contact_name_best TEXT,
          domain TEXT,
          organization_name_guess TEXT,
          total_emails INTEGER,
          last_seen_at TEXT,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          confidence_score REAL
        );
        CREATE TABLE organization_master (
          domain TEXT PRIMARY KEY,
          organization_name_guess TEXT,
          total_emails INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER
        );
        CREATE TABLE opportunity_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          signal_type TEXT NOT NULL,
          entity_kind TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          score REAL
        );
        CREATE TABLE emails (recipients TEXT, source_file TEXT, folder TEXT);
        CREATE TABLE contact_email_suppression (email TEXT PRIMARY KEY, suppression_reason_code TEXT);
        CREATE TABLE outreach_contact_state (contact_email_norm TEXT PRIMARY KEY, state TEXT);
        CREATE TABLE supplier_master (domain_norm TEXT);

        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_name TEXT NOT NULL,
          source_record_id TEXT,
          org_name TEXT,
          contact_name TEXT,
          email TEXT,
          email_norm TEXT,
          region TEXT,
          city TEXT,
          lead_type TEXT,
          equipment_match_tags TEXT,
          lab_context_score REAL,
          priority_score REAL,
          fit_bucket TEXT,
          evidence_summary TEXT,
          website TEXT,
          status TEXT,
          next_action TEXT,
          last_seen_at TEXT,
          upstream_sync_state TEXT
        );
        CREATE TABLE lead_matches_existing_orgs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_id INTEGER NOT NULL,
          matched_domain TEXT,
          matched_org_name TEXT,
          match_type TEXT,
          confidence_score REAL,
          already_in_archive_flag INTEGER
        );
        """
    )


def test_compare_archive_vs_lead_output_shape_and_overlap() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_common(conn)
    conn.execute(
        "INSERT INTO organization_master VALUES ('histuni.cl', 'Hist Uni', 80, 4, 1, 0)"
    )
    conn.executescript(
        """
        INSERT INTO contact_master VALUES
          ('alice@histuni.cl','Alice','histuni.cl','Hist Uni',35,'2025-03-01',2,0,0,0.9),
          ('bob@histuni.cl','Bob','histuni.cl','Hist Uni',20,'2025-02-01',1,0,0,0.7),
          ('sent@histuni.cl','Sent','histuni.cl','Hist Uni',40,'2025-04-01',2,0,0,0.9);
        INSERT INTO opportunity_signals (signal_type, entity_kind, entity_key, score)
          VALUES ('dormant_contact','contact','alice@histuni.cl',9.0);
        INSERT INTO emails VALUES ('sent@histuni.cl', 'gmail:contacto@origenlab.cl/1', '[Gmail]/Enviados');

        INSERT INTO lead_master (
          source_name, source_record_id, org_name, contact_name, email, email_norm, region, city,
          lead_type, equipment_match_tags, lab_context_score, priority_score, fit_bucket,
          evidence_summary, website, status, next_action, last_seen_at, upstream_sync_state
        ) VALUES
          ('src','1','Hist Uni','Alice','alice@histuni.cl','alice@histuni.cl','RM','SCL','public','eq',1.0,9.2,'high_fit','ev','', 'nuevo','', '2025-03-01','active'),
          ('src','2','Other Org','Carl','carl@other.cl','carl@other.cl','RM','SCL','public','eq',1.0,8.1,'high_fit','ev','', 'nuevo','', '2025-03-02','active');
        """
    )
    conn.commit()

    comp = compare_archive_vs_lead_outreach(
        conn,
        gmail_user="contacto@origenlab.cl",
        top_n=20,
        archive_limit=200,
        lead_limit=200,
    )
    assert comp.overlap_summary["archive_top_count"] >= 2
    assert comp.overlap_summary["lead_top_count"] >= 2
    assert comp.overlap_summary["overlap_email_count"] >= 1
    assert "sent_history" in comp.blocked_archive_by_reason
    assert all(r.source_label == SOURCE_LABEL_ARCHIVE for r in comp.archive_top)
    assert all(r.source_label == SOURCE_LABEL_LEAD for r in comp.lead_top)
    assert all(r.warmth_band in {"strong", "medium", "weak"} for r in comp.archive_top)
    assert all("warmth_" in r.quality_flags for r in comp.archive_top)
    assert all(r.quality_flags == "lead_queue" for r in comp.lead_top)
    d = comp.to_dict()
    assert {"archive_top", "lead_top", "overlap_summary", "blocked_archive_by_reason"} <= set(d.keys())
    conn.close()


def test_source_labels_are_stable() -> None:
    assert SOURCE_LABEL_ARCHIVE == "archive_contact_master"
    assert SOURCE_LABEL_LEAD == "lead_master"

