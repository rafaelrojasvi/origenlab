"""Tests for read-only SERVA/CEAF deal preview (SQLite + script safety)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.commercial.serva_ceaf_deal_preview import (
    DEAL_KEY,
    build_serva_ceaf_deal_preview,
    connect_sqlite_readonly,
    write_preview_outputs,
)


def _seed_deal_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          source_file TEXT NOT NULL,
          folder TEXT,
          message_id TEXT,
          subject TEXT,
          sender TEXT,
          recipients TEXT,
          date_iso TEXT,
          body_text_clean TEXT
        );
        CREATE TABLE attachments (
          id INTEGER PRIMARY KEY,
          email_id INTEGER NOT NULL,
          part_index INTEGER,
          filename TEXT,
          content_type TEXT
        );
        CREATE TABLE attachment_extracts (
          id INTEGER PRIMARY KEY,
          attachment_id INTEGER NOT NULL UNIQUE,
          extract_status TEXT,
          extract_method TEXT,
          text_preview TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, subject, sender, recipients, date_iso, body_text_clean)
        VALUES (1, 'gmail:test/INBOX', 'INBOX', 'Remite OC N º 26172', 'cgaray@ceaf.cl', 'contacto@origenlab.cl', '2026-05-14', '')
        """
    )
    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, subject, sender, recipients, date_iso, body_text_clean)
        VALUES (2, 'gmail:test/INBOX', 'INBOX', 'PO N°174-26 payment EUR 218,00', 'order@serva.de', 'contacto@origenlab.cl', '2026-05-15', 'customer 310471 A2602545')
        """
    )
    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, subject, sender, recipients, date_iso, body_text_clean)
        VALUES (3, 'gmail:test/INBOX', 'INBOX', 'Factura N°6 BancoChile', 'fgonzalez@ceaf.cl', 'contacto@origenlab.cl', '2026-05-16', '')
        """
    )
    conn.execute(
        "INSERT INTO attachments (id, email_id, part_index, filename) VALUES (10, 1, 0, 'OC N º 26172.pdf')"
    )
    conn.execute(
        "INSERT INTO attachments (id, email_id, part_index, filename) "
        "VALUES (11, 2, 0, 'A2602545 OrigenLab.pdf')"
    )
    conn.execute(
        "INSERT INTO attachments (id, email_id, part_index, filename) "
        "VALUES (12, 2, 1, 'wise_transfer_confirmation__transfer__2152655677.pdf')"
    )
    conn.execute(
        """
        INSERT INTO attachment_extracts (id, attachment_id, extract_status, extract_method, text_preview)
        VALUES (1, 11, 'success', 'pdf', 'Pro-forma A2602545 total EUR 363,00 freight 145')
        """
    )
    conn.commit()
    conn.close()


def test_build_preview_confirmed_financial_fields(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_deal_db(db)
    conn = connect_sqlite_readonly(db)
    try:
        preview = build_serva_ceaf_deal_preview(conn)
    finally:
        conn.close()

    assert preview["deal_key"] == DEAL_KEY
    fields = preview["fields"]
    assert fields["client_payment_received_clp"]["value"] == 1499400
    assert fields["client_sale_amount_net_clp"]["value"] in (1_260_000, "1260000")
    assert fields["client_iva_amount_clp"]["value"] in (239_400, "239400")
    assert float(fields["client_iva_rate"]["value"]) == 0.19
    assert preview["client_vat_breakdown"]["subtotal_net_clp"] == 1_260_000
    assert fields["supplier_invoice_total_eur"]["value"] == "363.00"
    assert fields["supplier_amount_paid_eur"]["value"] == "218.00"
    assert fields["reconciliation_status"]["value"] == "reconciled_excluding_supplier_freight"
    assert (
        preview["fields"]["deal_status"]["value"]
        == "paid_by_client__supplier_payment_sent__logistics_pending"
    )
    assert preview["reconciliation"]["freight_excluded_from_wire"] is True
    assert preview["evidence"]["email_count_total"] >= 3
    assert preview["safety"]["db_writes"] is False
    assert "public_export" in preview


def test_write_preview_outputs_three_files(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_deal_db(db)
    conn = connect_sqlite_readonly(db)
    preview = build_serva_ceaf_deal_preview(conn)
    conn.close()
    out = tmp_path / "commercial_deals_preview"
    json_path, csv_path, public_path = write_preview_outputs(preview, out)
    assert json_path.is_file()
    assert csv_path.is_file()
    assert public_path.is_file()
    assert "client_payment_received_clp" in csv_path.read_text(encoding="utf-8")


def test_extract_script_is_read_only_no_gmail_no_writes() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "commercial"
        / "extract_serva_ceaf_deal_preview.py"
    )
    text = script.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "mode=ro" in lowered or "readonly" in lowered
    assert "connect_sqlite_readonly" in text
    assert "--apply" not in text
    assert "gmail" not in lowered or "does not mutate gmail" in lowered
    forbidden = [
        "send_inline_html",
        "imaplib",
        "alembic upgrade",
        "sync_dashboard_postgres",
        "executescript(",
        "insert into",
    ]
    for token in forbidden:
        assert token.lower() not in lowered, f"unexpected token in script: {token}"
