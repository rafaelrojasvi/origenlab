"""Tests for contacted-universe audit (Phase 10A)."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.candidate_export_gate import REASON_SUPPRESSION
from origenlab_email_pipeline.leads.contacted_universe_audit import (
    NET_NEW_ALREADY_CONTACTED,
    NET_NEW_BOUNCED_BLOCK,
    NET_NEW_SAFE,
    NET_NEW_SAME_DOMAIN_REVIEW,
    NET_NEW_SUPPLIER_BLOCK,
    NET_NEW_SUPPRESSED_BLOCK,
    RECOMMENDED_ALREADY_CONTACTED,
    RECOMMENDED_BOUNCED,
    RECOMMENDED_SUPPLIER,
    build_contacted_universe,
    build_contacted_universe_context,
    build_filtered_exports,
    classify_contact_noise,
    classify_net_new_eligibility,
    connect_readonly,
)


def _seed_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recipients TEXT,
          sender TEXT,
          subject TEXT,
          source_file TEXT,
          folder TEXT,
          date_raw TEXT,
          date_iso TEXT
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
        CREATE TABLE contact_domain_suppression (
          domain_norm TEXT PRIMARY KEY,
          suppression_reason_text TEXT,
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
        CREATE TABLE supplier_master (
          domain_norm TEXT PRIMARY KEY
        );
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
        """
    )
    sent = "gmail:contacto@origenlab.cl/[Gmail]/Enviados"
    conn.execute(
        """
        INSERT INTO emails (recipients, sender, subject, source_file, folder, date_iso)
        VALUES (?, 'contacto@origenlab.cl', 'Cotización equipos', ?, '[Gmail]/Enviados', '2026-01-10T10:00:00Z')
        """,
        ("Buyer One <senthit@buyer.test>", sent),
    )
    conn.execute(
        """
        INSERT INTO emails (recipients, sender, subject, source_file, folder, date_iso)
        VALUES (?, 'contacto@origenlab.cl', 'Seguimiento', ?, '[Gmail]/Enviados', '2026-02-01T10:00:00Z')
        """,
        ("colleague@buyer.test", sent),
    )
    conn.execute(
        """
        INSERT INTO emails (sender, subject, source_file, folder, date_iso)
        VALUES ('replier@buyer.test', 'Re: Cotización', ?, 'INBOX', '2026-01-12T10:00:00Z')
        """,
        (sent.replace("Enviados", "INBOX"),),
    )
    conn.execute(
        """
        INSERT INTO contact_email_suppression (
          email, suppression_reason_code, suppression_reason_text,
          suppression_source, updated_at, updated_by
        ) VALUES (?, 'bounce_no_such_user', 'NDR', 'test', '2026-01-01T00:00:00Z', 'test')
        """,
        ("bounced@bad.test",),
    )
    conn.execute(
        """
        INSERT INTO contact_email_suppression (
          email, suppression_reason_code, suppression_reason_text,
          suppression_source, updated_at, updated_by
        ) VALUES (?, 'manual_do_not_contact', 'ops', 'test', '2026-01-01T00:00:00Z', 'test')
        """,
        ("blocked@manual.test",),
    )
    conn.execute(
        "INSERT INTO supplier_master (domain_norm) VALUES ('serva.de')"
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          organization_type_guess, total_emails, inbound_emails, outbound_emails
        ) VALUES (
          'vendor@serva.de', 'Vendor', 'serva.de', 'SERVA', 'supplier', 5, 5, 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO outreach_contact_state (
          contact_email_norm, state, first_contacted_at, last_contacted_at,
          source, updated_at, updated_by
        ) VALUES ('senthit@buyer.test', 'contacted', '2026-01-10', '2026-01-10', 'test', '2026-01-10', 'test')
        """
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          organization_type_guess, total_emails, inbound_emails, outbound_emails
        ) VALUES (
          'noreply@promo.test', '', 'promo.test', '', '', 1, 1, 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          organization_type_guess, total_emails, inbound_emails, outbound_emails
        ) VALUES (
          '987654321@verifiedsupplier.chinalabsupplies.com', '', 'verifiedsupplier.chinalabsupplies.com',
          '', '', 2, 2, 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          organization_type_guess, total_emails, inbound_emails, outbound_emails
        ) VALUES (
          'randomspam@xyz', '', 'xyz', '', '', 1, 1, 0
        )
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def audit_db(tmp_path: Path) -> Path:
    db = tmp_path / "audit.sqlite"
    _seed_db(db)
    return db


def _ctx(db: Path):
    conn = connect_readonly(db)
    try:
        ctx, _, _ = build_contacted_universe_context(
            conn,
            gmail_user="contacto@origenlab.cl",
            sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
        )
        return ctx
    finally:
        conn.close()


def test_sent_recipient_becomes_already_contacted(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    row = next(r for r in result.contacts if r["normalized_email"] == "senthit@buyer.test")
    assert row["recommended_status"] == RECOMMENDED_ALREADY_CONTACTED
    assert int(row["sent_count"]) >= 1


def test_bounced_email_becomes_bounced_do_not_contact(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    row = next(r for r in result.contacts if r["normalized_email"] == "bounced@bad.test")
    assert row["recommended_status"] == RECOMMENDED_BOUNCED
    assert row["bounced_bool"] == "true"


def test_supplier_domain_becomes_supplier_do_not_market(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    row = next(r for r in result.contacts if r["normalized_email"] == "vendor@serva.de")
    assert row["recommended_status"] == RECOMMENDED_SUPPLIER
    assert row["role_guess"] == "supplier"


def test_same_domain_gets_same_domain_contacted_review(audit_db: Path) -> None:
    ctx = _ctx(audit_db)
    assert classify_net_new_eligibility("newperson@buyer.test", ctx=ctx) == NET_NEW_SAME_DOMAIN_REVIEW


def test_net_new_lab_email_passes(audit_db: Path) -> None:
    ctx = _ctx(audit_db)
    assert classify_net_new_eligibility("labdirector@newuniversity.cl", ctx=ctx) == NET_NEW_SAFE


def test_suppression_overrides_everything(audit_db: Path) -> None:
    ctx = _ctx(audit_db)
    assert classify_net_new_eligibility("blocked@manual.test", ctx=ctx) == NET_NEW_SUPPRESSED_BLOCK
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    row = next(r for r in result.contacts if r["normalized_email"] == "blocked@manual.test")
    assert REASON_SUPPRESSION in row["reason_codes"]


def test_classify_bounced_block(audit_db: Path) -> None:
    ctx = _ctx(audit_db)
    assert classify_net_new_eligibility("bounced@bad.test", ctx=ctx) == NET_NEW_BOUNCED_BLOCK


def test_classify_supplier_block(audit_db: Path) -> None:
    ctx = _ctx(audit_db)
    assert classify_net_new_eligibility("sales@serva.de", ctx=ctx) == NET_NEW_SUPPLIER_BLOCK


def test_classify_already_contacted(audit_db: Path) -> None:
    ctx = _ctx(audit_db)
    assert classify_net_new_eligibility("senthit@buyer.test", ctx=ctx) == NET_NEW_ALREADY_CONTACTED


def test_summary_json_counts(audit_db: Path) -> None:
    conn = sqlite3.connect(str(audit_db))
    result = build_contacted_universe(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    assert result.summary["unique_outbound_recipient_emails"] >= 2
    assert result.summary["bounced_recipient_emails"] >= 1


def test_write_outputs(tmp_path: Path, audit_db: Path) -> None:
    from origenlab_email_pipeline.leads.contacted_universe_audit import write_contacted_universe_outputs

    conn = sqlite3.connect(str(audit_db))
    result = build_contacted_universe(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    out = tmp_path / "current"
    paths = write_contacted_universe_outputs(result, out)
    assert paths["contacts_csv"].is_file()
    assert paths["exact_emails_csv"].is_file()
    assert paths["noisy_contacts_csv"].is_file()
    with paths["contacts_csv"].open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert any(r["normalized_email"] == "senthit@buyer.test" for r in rows)


def test_raw_universe_includes_noisy_safety_contacts(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    emails = {r["normalized_email"] for r in result.contacts}
    assert "noreply@promo.test" in emails
    assert len(result.contacts) > len(result.filtered.exact_emails)


def test_exact_contacted_export_excludes_never_contacted_spam(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    exact = {r["normalized_email"] for r in result.filtered.exact_emails}
    assert "senthit@buyer.test" in exact
    assert "noreply@promo.test" not in exact
    assert "987654321@verifiedsupplier.chinalabsupplies.com" not in exact


def test_contacted_domain_export_includes_sent_domains(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    domains = {r["domain"] for r in result.filtered.domains_exclusion}
    assert "buyer.test" in domains
    assert int(next(r for r in result.filtered.domains_exclusion if r["domain"] == "buyer.test")["sent_count"]) >= 1


def test_noreply_goes_to_noisy_contacts_review(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    noisy = {r["normalized_email"] for r in result.filtered.noisy_contacts}
    assert "noreply@promo.test" in noisy
    row = next(r for r in result.filtered.noisy_contacts if r["normalized_email"] == "noreply@promo.test")
    assert "noise_local" in row["noise_reason_codes"]


def test_supplier_marketplace_goes_to_noisy_contacts_review(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    noisy = {r["normalized_email"] for r in result.filtered.noisy_contacts}
    assert "987654321@verifiedsupplier.chinalabsupplies.com" in noisy
    assert "noise_supplier_marketplace" in next(
        r for r in result.filtered.noisy_contacts
        if r["normalized_email"] == "987654321@verifiedsupplier.chinalabsupplies.com"
    )["noise_reason_codes"]


def test_follow_up_candidates_exclude_bounce_supplier_noise(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    follow = {r["normalized_email"] for r in result.filtered.follow_up_candidates}
    assert "bounced@bad.test" not in follow
    assert "vendor@serva.de" not in follow
    assert "noreply@promo.test" not in follow


def test_follow_up_candidates_include_replied_client(audit_db: Path) -> None:
    result = build_contacted_universe(
        sqlite3.connect(str(audit_db)),
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados", "[Gmail]/Sent Mail"),
    )
    follow = {r["normalized_email"] for r in result.filtered.follow_up_candidates}
    assert "replier@buyer.test" in follow


def test_classify_contact_noise_detects_noreply() -> None:
    noisy, reasons = classify_contact_noise(
        {
            "normalized_email": "noreply@acme.com",
            "domain": "acme.com",
            "display_name": "",
            "organization_name": "",
            "role_guess": "client",
            "sent_count": "0",
            "received_count": "0",
        }
    )
    assert noisy
    assert any("noise_local" in r for r in reasons)
