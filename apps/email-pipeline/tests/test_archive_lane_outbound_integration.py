"""Integration: canonical archive batch respects Sent ingest, outreach memory, and suppression."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from origenlab_email_pipeline.archive_send_batch_builder import (
    AUDIT_CSV_NAME,
    BUILD_SUMMARY_JSON_NAME,
    REVIEW_REQUIRED_CSV_NAME,
    SEND_READY_CSV_NAME,
    SHORTLIST_CSV_NAME,
    build_archive_send_batch,
)
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_OUTREACH_CONTACTED,
    REASON_SENT_HISTORY,
    REASON_SUPPRESSION,
)
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS

GMAIL = "contacto@origenlab.cl"
DOMAIN = "archlane.test"
ORG_NAME = "Arch Lane Org"


def _base_schema() -> str:
    return """
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
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recipients TEXT,
          source_file TEXT,
          folder TEXT,
          date_iso TEXT,
          date_raw TEXT
        );
        CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY,
          suppression_reason_code TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT
        );
        CREATE TABLE supplier_master (domain_norm TEXT);
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
        """


def _insert_contact(
    cur: sqlite3.Cursor,
    *,
    email: str,
    total_emails: int,
    quote_ct: int = 5,
) -> None:
    cur.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count, business_doc_email_count,
          quote_doc_count, invoice_doc_count, top_equipment_tags, confidence_score
        ) VALUES (?, ?, ?, ?, 'business', '2021-01-01', '2026-04-15T12:00:00+00:00',
                  ?, 5, 5, ?, 0, 0, 0, 0, 0, '', 0.85)
        """,
        (email, "Contact", DOMAIN, ORG_NAME, total_emails, quote_ct),
    )


def _seed_archive_blocker_memory_db(path: Path) -> None:
    """One survivor + Sent-blocked + contacted + suppression (canonical gate blockers)."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_base_schema())
        conn.execute(
            """
            INSERT INTO organization_master (
              domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
              total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
              business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
            ) VALUES (?, ?, 'business', '2021-01-01', '2026-01-01', 200, 5, 10, 2, 2,
                      0, 0, 0, '', '')
            """,
            (DOMAIN, ORG_NAME),
        )
        survive = f"survive@{DOMAIN}"
        in_sent = f"in_sent@{DOMAIN}"
        contacted = f"contacted@{DOMAIN}"
        suppressed = f"suppressed@{DOMAIN}"
        _insert_contact(conn.cursor(), email=survive, total_emails=500)
        _insert_contact(conn.cursor(), email=in_sent, total_emails=400)
        _insert_contact(conn.cursor(), email=contacted, total_emails=300)
        _insert_contact(conn.cursor(), email=suppressed, total_emails=200)
        conn.execute(
            """
            INSERT INTO emails (source_file, folder, recipients, date_iso)
            VALUES (?, '[Gmail]/Enviados', ?, '2026-04-14T12:00:00+00:00')
            """,
            (f"gmail:{GMAIL}/sent1", in_sent),
        )
        conn.execute(
            "INSERT INTO outreach_contact_state (contact_email_norm, state) VALUES (?, 'contacted')",
            (contacted,),
        )
        conn.execute(
            "INSERT INTO contact_email_suppression (email, suppression_reason_code) VALUES (?, 'manual')",
            (suppressed,),
        )
        conn.execute(
            """
            INSERT INTO contact_candidate (
              contact_email, org_domain, status, suppression_flags, rationale_text,
              confidence_score, strength_score, evidence_count, created_at, updated_at
            ) VALUES (?, ?, 'approved', '', 'fixture', 0.9, 0.9, 2, 't', 't')
            """,
            (survive, DOMAIN),
        )
        conn.commit()
    finally:
        conn.close()


def test_build_archive_send_batch_blocks_sent_outreach_suppression(
    tmp_path: Path,
) -> None:
    """Canonical `build_archive_send_batch` drops blocker-memory rows before send_ready."""
    db = tmp_path / "archive.sqlite"
    out_dir = tmp_path / "out"
    _seed_archive_blocker_memory_db(db)
    survive = f"survive@{DOMAIN}"
    blocked = {
        f"in_sent@{DOMAIN}",
        f"contacted@{DOMAIN}",
        f"suppressed@{DOMAIN}",
    }

    conn = sqlite3.connect(str(db))
    try:
        result = build_archive_send_batch(
            conn=conn,
            db_path=db,
            out_dir=out_dir,
            gmail_user=GMAIL,
            fetch_cap=80,
            audit_limit=20,
            shortlist_limit=10,
            sent_folders=DEFAULT_SENT_FOLDERS,
            strict_contact_graph_noise=True,
            allow_weak_warmth=True,
            skip_commercial_precheck=False,
            audit_only=False,
            sent_folder_defaults_used=False,
        )
    finally:
        conn.close()

    summary = result.summary
    assert summary["archive_eligible_rows"] == 1
    assert summary["archive_blocked_rows"] == 3
    assert summary["shortlist_rows"] == 1
    assert summary["send_ready_rows"] == 1
    assert summary["gate_blocked_rows"] == 0
    assert summary["final_drop_rows"] == 0

    send_path = out_dir / SEND_READY_CSV_NAME
    assert send_path.is_file()
    with send_path.open(encoding="utf-8", newline="") as f:
        send_rows = list(csv.DictReader(f))
    assert len(send_rows) == 1
    assert send_rows[0]["contact_email"].lower() == survive
    for em in blocked:
        assert em not in {r["contact_email"].lower() for r in send_rows}

    with (out_dir / REVIEW_REQUIRED_CSV_NAME).open(encoding="utf-8", newline="") as f:
        review_rows = list(csv.DictReader(f))
    assert survive not in {r.get("contact_email", "").lower() for r in review_rows}

    short_path = out_dir / SHORTLIST_CSV_NAME
    with short_path.open(encoding="utf-8", newline="") as f:
        short_rows = list(csv.DictReader(f))
    assert len(short_rows) == 1
    assert short_rows[0]["contact_email"].lower() == survive

    audit_path = out_dir / AUDIT_CSV_NAME
    with audit_path.open(encoding="utf-8", newline="") as f:
        audit_rows = list(csv.DictReader(f))
    by_email = {r["contact_email"].lower(): r for r in audit_rows}
    assert by_email[survive]["eligible"].lower() == "true"
    assert by_email[f"in_sent@{DOMAIN}"]["eligible"].lower() == "false"
    assert REASON_SENT_HISTORY in (by_email[f"in_sent@{DOMAIN}"]["reject_reason_code"] or "")
    assert by_email[f"contacted@{DOMAIN}"]["eligible"].lower() == "false"
    assert REASON_OUTREACH_CONTACTED in (by_email[f"contacted@{DOMAIN}"]["reject_reason_code"] or "")
    assert by_email[f"suppressed@{DOMAIN}"]["eligible"].lower() == "false"
    assert REASON_SUPPRESSION in (by_email[f"suppressed@{DOMAIN}"]["reject_reason_code"] or "")

    built = json.loads((out_dir / BUILD_SUMMARY_JSON_NAME).read_text(encoding="utf-8"))
    assert built["outbound_run"]["lane"] == "archive"
    assert built["outbound_run"]["sent_folders_resolved"] == list(DEFAULT_SENT_FOLDERS)


def _seed_sent_folder_mismatch_db(path: Path) -> None:
    """`drafts_only` appears only in a non-Sent folder row; `sentblocked` in Enviados."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_base_schema())
        conn.execute(
            """
            INSERT INTO organization_master (
              domain, organization_name_guess, organization_type_guess, first_seen_at, last_seen_at,
              total_emails, total_contacts, quote_email_count, invoice_email_count, purchase_email_count,
              business_doc_email_count, quote_doc_count, invoice_doc_count, top_equipment_tags, key_contacts
            ) VALUES (?, ?, 'business', '2021-01-01', '2026-01-01', 200, 5, 10, 2, 2,
                      0, 0, 0, '', '')
            """,
            (DOMAIN, ORG_NAME),
        )
        drafts_only = f"drafts_only@{DOMAIN}"
        sentblocked = f"sentblocked@{DOMAIN}"
        _insert_contact(conn.cursor(), email=drafts_only, total_emails=260)
        _insert_contact(conn.cursor(), email=sentblocked, total_emails=240)
        conn.execute(
            """
            INSERT INTO emails (source_file, folder, recipients, date_iso)
            VALUES (?, '[Gmail]/Drafts', ?, '2026-04-14T12:00:00+00:00')
            """,
            (f"gmail:{GMAIL}/dr", drafts_only),
        )
        conn.execute(
            """
            INSERT INTO emails (source_file, folder, recipients, date_iso)
            VALUES (?, '[Gmail]/Enviados', ?, '2026-04-14T12:00:00+00:00')
            """,
            (f"gmail:{GMAIL}/sn", sentblocked),
        )
        for em in (drafts_only, sentblocked):
            conn.execute(
                """
                INSERT INTO contact_candidate (
                  contact_email, org_domain, status, suppression_flags, rationale_text,
                  confidence_score, strength_score, evidence_count, created_at, updated_at
                ) VALUES (?, ?, 'approved', '', 'fixture', 0.9, 0.9, 2, 't', 't')
                """,
                (em, DOMAIN),
            )
        conn.commit()
    finally:
        conn.close()


def test_archive_sent_history_only_default_sent_folders_not_drafts(tmp_path: Path) -> None:
    """Mail under non-configured folders (e.g. Drafts) does not populate Sent-history norms."""
    db = tmp_path / "mismatch.sqlite"
    out_dir = tmp_path / "out2"
    _seed_sent_folder_mismatch_db(db)
    drafts_only = f"drafts_only@{DOMAIN}"
    sentblocked = f"sentblocked@{DOMAIN}"

    conn = sqlite3.connect(str(db))
    try:
        build_archive_send_batch(
            conn=conn,
            db_path=db,
            out_dir=out_dir,
            gmail_user=GMAIL,
            fetch_cap=40,
            audit_limit=10,
            shortlist_limit=5,
            sent_folders=DEFAULT_SENT_FOLDERS,
            strict_contact_graph_noise=True,
            allow_weak_warmth=True,
            skip_commercial_precheck=False,
            audit_only=False,
            sent_folder_defaults_used=False,
        )
    finally:
        conn.close()

    with (out_dir / AUDIT_CSV_NAME).open(encoding="utf-8", newline="") as f:
        audit_rows = list(csv.DictReader(f))
    by_email = {r["contact_email"].lower(): r for r in audit_rows}
    assert by_email[drafts_only]["eligible"].lower() == "true"
    assert by_email[sentblocked]["eligible"].lower() == "false"
    assert REASON_SENT_HISTORY in (by_email[sentblocked]["reject_reason_code"] or "")

    with (out_dir / SEND_READY_CSV_NAME).open(encoding="utf-8", newline="") as f:
        send_rows = list(csv.DictReader(f))
    emails_out = {r["contact_email"].lower() for r in send_rows}
    assert drafts_only in emails_out
    assert sentblocked not in emails_out
