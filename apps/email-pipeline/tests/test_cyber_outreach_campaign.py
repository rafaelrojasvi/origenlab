"""Cyber outreach campaign builder — read-only segmentation and gate routing."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.campaigns.cyber_campaign_templates import (
    template_net_new_cyber_es,
    template_warm_follow_up_es,
)
from origenlab_email_pipeline.campaigns.cyber_campaign_types import (
    CYBER_CAMPAIGN_SLUG,
    SAFETY_BLOCKED,
    SAFETY_ELIGIBLE,
    SAFETY_SAME_DOMAIN,
    SEGMENT_EXCLUDED,
    SEGMENT_NET_NEW,
    SEGMENT_PREVIOUS,
    SEGMENT_SAME_DOMAIN,
    SEGMENT_WARM,
)
from origenlab_email_pipeline.campaigns.cyber_outreach_campaign import (
    build_cyber_outreach_campaign,
    write_cyber_campaign_outputs,
)
from origenlab_email_pipeline.candidate_export_gate import REASON_SENT_HISTORY


def _seed_minimal(conn: sqlite3.Connection) -> None:
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
        CREATE TABLE lead_matches_existing_orgs (
          id INTEGER PRIMARY KEY,
          lead_id INTEGER,
          matched_org_name TEXT,
          already_in_archive_flag INTEGER
        );
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY,
          source_name TEXT,
          org_name TEXT,
          contact_name TEXT,
          email TEXT,
          email_norm TEXT,
          region TEXT,
          city TEXT,
          lead_type TEXT,
          priority_score REAL,
          fit_bucket TEXT,
          evidence_summary TEXT,
          website TEXT,
          last_seen_at TEXT,
          equipment_match_tags TEXT,
          lab_context_score REAL,
          status TEXT DEFAULT 'active',
          upstream_sync_state TEXT DEFAULT 'active'
        );
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          date_iso TEXT,
          date_raw TEXT,
          subject TEXT,
          sender TEXT,
          recipients TEXT,
          source_file TEXT,
          folder TEXT
        );
        CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY,
          suppression_reason_code TEXT NOT NULL,
          suppression_reason_text TEXT,
          suppression_source TEXT,
          last_bounced_at TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          first_contacted_at TEXT,
          last_contacted_at TEXT,
          source TEXT,
          notes TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT,
          lead_id INTEGER
        );
        """
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          last_seen_at, total_emails, quote_email_count, purchase_email_count, confidence_score
        ) VALUES (
          'warm.quote@lab-univ.cl', 'Ana Warm', 'lab-univ.cl', 'Lab Universidad',
          '2026-05-01', 12, 3, 1, 0.8
        )
        """
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          last_seen_at, total_emails, quote_email_count, purchase_email_count, confidence_score
        ) VALUES (
          'buyer@hospital-prev.cl', 'Carlos Compra', 'hospital-prev.cl', 'Hospital Previo',
          '2026-05-10', 20, 1, 5, 0.9
        )
        """
    )
    conn.execute(
        """
        INSERT INTO organization_master (domain, organization_name_guess, total_emails, purchase_email_count)
        VALUES ('hospital-prev.cl', 'Hospital Previo', 20, 5)
        """
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          id, source_name, org_name, contact_name, email, email_norm,
          priority_score, fit_bucket, status, upstream_sync_state
        ) VALUES (
          1, 'test', 'Clínica Nueva', 'Pat Nueva', 'nueva@clinica-nueva.cl', 'nueva@clinica-nueva.cl',
          85, 'high_fit', 'active', 'active'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO emails (date_iso, subject, sender, recipients, source_file, folder)
        VALUES (
          '2026-04-01T10:00:00',
          'Cotización equipos',
          'contacto@origenlab.cl',
          'warm.quote@lab-univ.cl',
          'gmail:contacto@origenlab.cl/[Gmail]/Enviados',
          '[Gmail]/Enviados'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO contact_email_suppression (
          email, suppression_reason_code, updated_at, updated_by
        ) VALUES ('blocked@spam.cl', 'manual_block', '2026-01-01', 'test')
        """
    )
    conn.commit()


def test_templates_include_opt_out_and_cyber_wording() -> None:
    subj, body = template_warm_follow_up_es(
        contact_name="Ana",
        organization="Lab Test",
        product_angle="Microscopía",
    )
    assert "Cyber" in subj
    assert "remover" in body
    assert "5–10%" in body or "5-10%" in body
    assert "catálogo" in body.lower()


def test_build_routes_sent_history_to_excluded(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _seed_minimal(conn)
        result = build_cyber_outreach_campaign(
            conn,
            gmail_user="contacto@origenlab.cl",
            sent_folders=("[Gmail]/Enviados",),
            warm_archive_scan_limit=50,
            net_new_limit=10,
        )
    finally:
        conn.close()

    assert result.summary["campaign_slug"] == CYBER_CAMPAIGN_SLUG
    assert result.summary["read_only"] is True
    blocked_emails = {r.email for r in result.excluded}
    assert "warm.quote@lab-univ.cl" in blocked_emails
    warm_row = next(r for r in result.excluded if r.email == "warm.quote@lab-univ.cl")
    assert "Enviados" in warm_row.exclusion_reason or REASON_SENT_HISTORY in warm_row.exclusion_reason

    paths = write_cyber_campaign_outputs(result, tmp_path)
    assert paths["warm"].is_file()
    assert paths["excluded"].is_file()
    warm_emails = {r.email for r in result.warm}
    assert "warm.quote@lab-univ.cl" not in warm_emails


def test_same_domain_review_when_domain_sent_not_email(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _seed_minimal(conn)
        conn.execute(
            """
                INSERT INTO contact_master (
                  email, contact_name_best, domain, organization_name_guess,
                  last_seen_at, total_emails, quote_email_count, purchase_email_count,
                  confidence_score
                ) VALUES (
                  'otro@lab-univ.cl', 'Otro Contacto', 'lab-univ.cl', 'Lab Universidad',
                  '2026-05-02', 40, 8, 2, 0.85
                )
            """
        )
        conn.commit()
        result = build_cyber_outreach_campaign(
            conn,
            gmail_user="contacto@origenlab.cl",
            sent_folders=("[Gmail]/Enviados",),
            warm_archive_scan_limit=50,
            net_new_limit=5,
        )
        same = {r.email for r in result.same_domain}
        assert "otro@lab-univ.cl" in same
        assert all(r.safety_status == SAFETY_SAME_DOMAIN for r in result.same_domain if r.email == "otro@lab-univ.cl")
    finally:
        conn.close()


def test_net_new_eligible_when_gate_passes() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _seed_minimal(conn)
        result = build_cyber_outreach_campaign(
            conn,
            gmail_user="contacto@origenlab.cl",
            sent_folders=("[Gmail]/Enviados",),
            warm_archive_scan_limit=30,
            net_new_limit=5,
        )
        net_emails = {r.email for r in result.net_new}
        assert "nueva@clinica-nueva.cl" in net_emails
        row = next(r for r in result.net_new if r.email == "nueva@clinica-nueva.cl")
        assert row.safety_status == SAFETY_ELIGIBLE
        assert row.segment == SEGMENT_NET_NEW
        subj, _ = template_net_new_cyber_es(
            contact_name=row.contact_name,
            organization=row.organization,
            product_angle=row.product_angle,
        )
        assert row.suggested_subject == subj
    finally:
        conn.close()
