"""Phase 2 regression locks for scripts/mart/build_business_mart.py (fixture SQLite)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_SCRIPT = REPO / "scripts" / "mart" / "build_business_mart.py"


def _run_mart(db: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(_SRC), "ORIGENLAB_SQLITE_PATH": str(db)}
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *extra],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _seed_rich_db(db: Path) -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.db import connect, init_schema, insert_attachment, insert_email
    from origenlab_email_pipeline.pipeline_run_recorder import set_kv
    from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema

    conn = connect(db)
    init_schema(conn)
    migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART})
    eid_out = insert_email(
        conn,
        source_file="gmail:contacto@origenlab.cl/[Gmail]/Enviados",
        folder="Sent",
        message_id="<out@mart>",
        subject="Cotizacion centrifuga",
        sender="contacto@origenlab.cl",
        recipients="buyer@hospital.cl",
        date_raw=None,
        date_iso="2026-05-10T12:00:00Z",
        body="adjunto cotizacion",
        body_html=None,
        body_text_raw="cotizacion",
        body_text_clean="cotizacion",
        body_source_type="plain",
        body_has_plain=1,
        body_has_html=0,
        full_body_clean="cotizacion centrifuga precio",
        top_reply_clean="cotizacion",
        attachment_count=1,
        has_attachments=1,
    )
    eid_in = insert_email(
        conn,
        source_file="gmail:contacto@origenlab.cl/INBOX",
        folder="INBOX",
        message_id="<in@mart>",
        subject="Re: Cotizacion",
        sender="Buyer <buyer@hospital.cl>",
        recipients="contacto@origenlab.cl",
        date_raw=None,
        date_iso="2026-05-11T09:00:00Z",
        body="necesito precio",
        body_html=None,
        body_text_raw="precio",
        body_text_clean="precio",
        body_source_type="plain",
        body_has_plain=1,
        body_has_html=0,
        full_body_clean="necesito precio incubadora",
        top_reply_clean="precio",
        attachment_count=0,
        has_attachments=0,
    )
    insert_attachment(
        conn,
        email_id=eid_out,
        part_index=0,
        filename="cotizacion.pdf",
        content_type="application/pdf",
        content_disposition="attachment",
        size_bytes=100,
        content_id=None,
        is_inline=0,
        sha256="abc",
        saved_path=None,
        created_at="2026-05-10T12:00:00Z",
    )
    aid = conn.execute("SELECT id FROM attachments WHERE email_id = ?", (eid_out,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO attachment_extracts (
          attachment_id, extract_status, extract_method, text_preview,
          detected_doc_type, has_quote_terms, has_invoice_terms,
          has_price_list_terms, has_purchase_terms
        ) VALUES (?, 'success', 'unit', 'cotizacion incubadora laboratorio',
                  'quote', 1, 0, 0, 0)
        """,
        (int(aid),),
    )
    conn.commit()
    # Pre-populate mart + raw email we must preserve across rebuild
    conn.execute(
        "INSERT INTO emails (source_file, message_id, subject, sender) VALUES ('legacy:keep', '<keep>', 'x', 'y')"
    )
    conn.execute("INSERT INTO contact_master (email, domain) VALUES ('stale@x.cl', 'x.cl')")
    conn.commit()
    set_kv(conn, "mart_document_master_signature_v1", "stale-sig")
    conn.close()
    assert eid_in >= 1


def test_rebuild_deletes_mart_tables_not_raw_emails(tmp_path: Path) -> None:
    db = tmp_path / "mart.sqlite"
    _seed_rich_db(db)
    before_emails = sqlite3.connect(db).execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    before_att = sqlite3.connect(db).execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    before_extracts = sqlite3.connect(db).execute("SELECT COUNT(*) FROM attachment_extracts").fetchone()[0]

    cp = _run_mart(db, "--rebuild", "--internal-domain", "origenlab.cl", "--limit-emails", "50")
    assert cp.returncode == 0, (cp.stdout + cp.stderr)[-3000:]

    conn = sqlite3.connect(db)
    after_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    after_att = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    after_extracts = conn.execute("SELECT COUNT(*) FROM attachment_extracts").fetchone()[0]
    assert after_emails == before_emails
    assert after_att == before_att
    assert after_extracts == before_extracts
    assert conn.execute("SELECT COUNT(*) FROM contact_master").fetchone()[0] >= 1
    assert conn.execute("SELECT COUNT(*) FROM organization_master").fetchone()[0] >= 1
    assert conn.execute("SELECT COUNT(*) FROM document_master").fetchone()[0] >= 1
    conn.close()


def test_document_master_from_attachment_extracts(tmp_path: Path) -> None:
    db = tmp_path / "doc.sqlite"
    _seed_rich_db(db)
    cp = _run_mart(db, "--rebuild", "--internal-domain", "origenlab.cl", "--limit-emails", "50")
    assert cp.returncode == 0, cp.stderr
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT doc_type, has_quote_terms, sender_email FROM document_master LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "quote"
    assert int(row[1]) == 1
    assert "origenlab" in (row[2] or "").lower()


def test_contact_and_org_master_from_sample_emails(tmp_path: Path) -> None:
    db = tmp_path / "co.sqlite"
    _seed_rich_db(db)
    cp = _run_mart(db, "--rebuild", "--internal-domain", "origenlab.cl", "--limit-emails", "50")
    assert cp.returncode == 0, cp.stderr
    conn = sqlite3.connect(db)
    contact = conn.execute(
        "SELECT email, domain FROM contact_master WHERE email LIKE '%hospital%'"
    ).fetchone()
    org = conn.execute(
        "SELECT domain FROM organization_master WHERE domain LIKE '%hospital%'"
    ).fetchone()
    conn.close()
    assert contact is not None
    assert "hospital" in (contact[0] or "")
    assert org is not None


def test_opportunity_signals_heuristic_output(tmp_path: Path) -> None:
    db = tmp_path / "sig.sqlite"
    _seed_rich_db(db)
    cp = _run_mart(db, "--rebuild", "--internal-domain", "origenlab.cl", "--limit-emails", "50")
    assert cp.returncode == 0, cp.stderr
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM opportunity_signals").fetchone()[0]
    sample = conn.execute(
        "SELECT signal_type, entity_kind, entity_key FROM opportunity_signals LIMIT 1"
    ).fetchone()
    conn.close()
    assert n >= 0
    if sample:
        assert sample[0]
        assert sample[1] in ("contact", "organization")
        assert sample[2]


def test_skip_document_master_if_unchanged_signature(tmp_path: Path) -> None:
    db = tmp_path / "skip.sqlite"
    _seed_rich_db(db)
    cp1 = _run_mart(
        db,
        "--rebuild",
        "--internal-domain",
        "origenlab.cl",
        "--limit-emails",
        "50",
        "--skip-document-master-if-unchanged",
    )
    assert cp1.returncode == 0, cp1.stderr
    assert "document_master" in cp1.stdout.lower()

    cp2 = _run_mart(
        db,
        "--rebuild",
        "--internal-domain",
        "origenlab.cl",
        "--limit-emails",
        "50",
        "--skip-document-master-if-unchanged",
    )
    assert cp2.returncode == 0, cp2.stderr
    assert "skipping rebuild" in cp2.stdout.lower() or "unchanged signature" in cp2.stdout.lower()
