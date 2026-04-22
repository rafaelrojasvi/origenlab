"""DB-backed integration: canonical lead queue respects Sent ingest + outreach sidecars."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.next_marketing_queue import compute_next_marketing_recipients


def _outbound_sidecar_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            folder TEXT,
            recipients TEXT,
            date_iso TEXT,
            date_raw TEXT
        );
        CREATE TABLE IF NOT EXISTS contact_email_suppression (email TEXT);
        CREATE TABLE IF NOT EXISTS outreach_contact_state (
            contact_email_norm TEXT,
            state TEXT
        );
        CREATE TABLE IF NOT EXISTS supplier_master (domain_norm TEXT);
        CREATE TABLE IF NOT EXISTS lead_contact_research (
            lead_id INTEGER PRIMARY KEY,
            contact_research_status TEXT NOT NULL DEFAULT 'nuevo',
            resolved_domain TEXT,
            resolved_contact_name TEXT,
            resolved_contact_email TEXT,
            contact_source TEXT,
            contact_research_notes TEXT,
            updated_at TEXT,
            updated_by TEXT
        );
        """
    )


def test_compute_next_marketing_excludes_sent_history_and_contacted_states(tmp_path: Path) -> None:
    db = tmp_path / "leads.sqlite"
    conn = sqlite3.connect(str(db))
    try:
        ensure_leads_tables(conn, backfill_norms=False, refresh_view=False)
        _outbound_sidecar_tables(conn)
        conn.executescript(
            """
            INSERT INTO lead_master (
              source_name, source_record_id, org_name, contact_name,
              email, email_norm, fit_bucket, priority_score, status, last_seen_at
            ) VALUES
              ('test', 'k1', 'Good Org', 'Alice',
               'good@keep.cl', 'good@keep.cl', 'high_fit', 10.0, 'nuevo',
               '2026-04-15T10:00:00+00:00'),
              ('test', 'k2', 'Sent Org', 'Bob',
               'in_sent@block.cl', 'in_sent@block.cl', 'high_fit', 9.0, 'nuevo',
               '2026-04-15T10:00:00+00:00'),
              ('test', 'k3', 'Contacted Org', 'Carol',
               'contacted@block.cl', 'contacted@block.cl', 'high_fit', 9.0, 'nuevo',
               '2026-04-15T10:00:00+00:00'),
              ('test', 'k4', 'Research Org', '',
               '', '', 'high_fit', 8.0, 'nuevo',
               '2026-04-15T10:00:00+00:00'),
              ('test', 'k5', 'Discarded Org', '',
               '', '', 'high_fit', 8.0, 'nuevo',
               '2026-04-15T10:00:00+00:00');

            INSERT INTO emails (source_file, folder, recipients, date_iso)
            VALUES (
              'gmail:contacto@origenlab.cl/t1',
              '[Gmail]/Enviados',
              'in_sent@block.cl',
              '2026-04-14T12:00:00+00:00'
            );

            INSERT INTO outreach_contact_state (contact_email_norm, state)
            VALUES ('contacted@block.cl', 'contacted');

            INSERT INTO lead_contact_research (
              lead_id, contact_research_status, resolved_contact_email, resolved_domain, updated_at
            ) VALUES
              (4, 'contacto_encontrado', 'research@new.cl', 'new.cl', '2026-04-15T11:00:00+00:00'),
              (5, 'descartado', 'discarded@new.cl', 'new.cl', '2026-04-15T11:00:00+00:00');
            """
        )
        conn.commit()

        rows, stats = compute_next_marketing_recipients(
            conn,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            limit=10,
            fetch_cap=50,
        )
    finally:
        conn.close()

    assert stats.n_scanned >= 4
    assert stats.n_kept == 2
    assert [r["contact_email"] for r in rows] == ["good@keep.cl", "research@new.cl"]
    by_email = {r["contact_email"]: r for r in rows}
    assert by_email["good@keep.cl"]["email_source"] == "lead_master"
    assert by_email["research@new.cl"]["email_source"] == "lead_contact_research"


def test_compute_next_marketing_dedupes_duplicate_researched_emails_deterministically(
    tmp_path: Path,
) -> None:
    db = tmp_path / "leads.sqlite"
    conn = sqlite3.connect(str(db))
    try:
        ensure_leads_tables(conn, backfill_norms=False, refresh_view=False)
        _outbound_sidecar_tables(conn)
        conn.executescript(
            """
            INSERT INTO lead_master (
              source_name, source_record_id, org_name, contact_name,
              email, email_norm, fit_bucket, priority_score, status, last_seen_at
            ) VALUES
              ('test', 'd1', 'Dup Org A', '',
               '', '', 'high_fit', 9.0, 'nuevo',
               '2026-04-15T10:00:00+00:00'),
              ('test', 'd2', 'Dup Org B', '',
               '', '', 'high_fit', 7.0, 'nuevo',
               '2026-04-15T09:00:00+00:00');

            INSERT INTO lead_contact_research (
              lead_id, contact_research_status, resolved_contact_email, resolved_domain, updated_at
            ) VALUES
              (1, 'contacto_encontrado', 'same@dup.cl', 'dup.cl', '2026-04-15T11:00:00+00:00'),
              (2, 'contacto_encontrado', 'same@dup.cl', 'dup.cl', '2026-04-15T11:00:00+00:00');
            """
        )
        conn.commit()
        rows, stats = compute_next_marketing_recipients(
            conn,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            limit=10,
            fetch_cap=50,
        )
    finally:
        conn.close()

    assert stats.n_scanned >= 2
    assert stats.n_kept == 1
    assert [r["contact_email"] for r in rows] == ["same@dup.cl"]
    # Higher-priority lead (priority_score 9.0) should win deterministically.
    assert rows[0]["id_lead"] == 1
    assert rows[0]["email_source"] == "lead_contact_research"
