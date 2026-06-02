from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "export_email_conversation_intelligence.py"

LOCKED_REAL_CLIENT_COLUMNS = [
    "organization",
    "domain",
    "contact_email",
    "contact_name",
    "sector",
    "region",
    "city",
    "first_outbound_date",
    "first_inbound_date",
    "last_interaction_date",
    "sent_count",
    "received_count",
    "status",
    "product_or_need",
    "summary",
    "recommended_next_action",
    "confidence",
]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _build_min_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            folder TEXT,
            message_id TEXT,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            date_iso TEXT,
            top_reply_clean TEXT,
            body_text_clean TEXT,
            full_body_clean TEXT
        );
        CREATE TABLE contact_master (
            email TEXT,
            contact_name_best TEXT,
            domain TEXT,
            organization_name_guess TEXT,
            quote_email_count INTEGER,
            invoice_email_count INTEGER,
            purchase_email_count INTEGER
        );
        CREATE TABLE organization_master (
            domain TEXT,
            organization_name_guess TEXT,
            organization_type_guess TEXT
        );
        CREATE TABLE lead_master (
            email_norm TEXT,
            org_name TEXT,
            contact_name TEXT,
            organization_type_guess TEXT,
            region TEXT,
            city TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO emails (id, source_file, folder, message_id, subject, sender, recipients, date_iso, top_reply_clean, body_text_clean, full_body_clean)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                "gmail:contacto@origenlab.cl/[Gmail]/Enviados",
                "[Gmail]/Enviados",
                "<1@example>",
                "Cotizacion incubadora",
                "contacto@origenlab.cl",
                "ana@cliente.cl",
                "2026-04-10T10:00:00+00:00",
                "Hola Ana, adjunto informacion.",
                "",
                "",
            ),
            (
                2,
                "gmail:contacto@origenlab.cl/INBOX",
                "INBOX",
                "<2@example>",
                "Re: Cotizacion incubadora",
                "Ana Cliente <ana@cliente.cl>",
                "contacto@origenlab.cl",
                "2026-04-11T11:00:00+00:00",
                "Necesito precio y disponibilidad.",
                "",
                "",
            ),
            (
                3,
                "gmail:contacto@origenlab.cl/INBOX",
                "INBOX",
                "<3@example>",
                "Delivery Status Notification",
                "MAILER-DAEMON <mailer-daemon@googlemail.com>",
                "contacto@origenlab.cl",
                "2026-04-12T11:00:00+00:00",
                "Undeliverable message.",
                "",
                "",
            ),
        ],
    )
    conn.execute(
        """
        INSERT INTO contact_master (email, contact_name_best, domain, organization_name_guess, quote_email_count, invoice_email_count, purchase_email_count)
        VALUES ('ana@cliente.cl', 'Ana Cliente', 'cliente.cl', 'Cliente SpA', 2, 0, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO organization_master (domain, organization_name_guess, organization_type_guess)
        VALUES ('cliente.cl', 'Cliente SpA', 'business')
        """
    )
    conn.commit()
    conn.close()


def test_export_email_conversation_intelligence_include_legacy_sources(tmp_path: Path) -> None:
    db = tmp_path / "emails2.sqlite"
    out = tmp_path / "out2"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            folder TEXT,
            message_id TEXT,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            date_iso TEXT,
            top_reply_clean TEXT,
            body_text_clean TEXT,
            full_body_clean TEXT
        );
        CREATE TABLE contact_master (email TEXT);
        CREATE TABLE organization_master (domain TEXT);
        CREATE TABLE lead_master (email_norm TEXT);
        """
    )
    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, message_id, subject, sender, recipients, date_iso, top_reply_clean, body_text_clean, full_body_clean)
        VALUES (1, '/mbox/contacto@labdelivery.cl/Inbox/mbox', 'INBOX', '<x>', 'Hola', 'contacto@origenlab.cl', 'z@w.cl', '2026-04-10T10:00:00+00:00', 'c', '', '')
        """
    )
    conn.commit()
    conn.close()
    res = _run(
        "--db",
        str(db),
        "--gmail-user",
        "contacto@origenlab.cl",
        "--out-dir",
        str(out),
        "--include-legacy-email-sources",
    )
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["overall"]["total_sent"] >= 1


def test_export_email_conversation_intelligence_default_excludes_legacy_only_sources(tmp_path: Path) -> None:
    db = tmp_path / "emails3.sqlite"
    out = tmp_path / "out3"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            folder TEXT,
            message_id TEXT,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            date_iso TEXT,
            top_reply_clean TEXT,
            body_text_clean TEXT,
            full_body_clean TEXT
        );
        CREATE TABLE contact_master (email TEXT);
        CREATE TABLE organization_master (domain TEXT);
        CREATE TABLE lead_master (email_norm TEXT);
        """
    )
    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, message_id, subject, sender, recipients, date_iso, top_reply_clean, body_text_clean, full_body_clean)
        VALUES (1, '/mbox/contacto@labdelivery.cl/Inbox/mbox', 'INBOX', '<x>', 'Hola', 'contacto@origenlab.cl', 'z@w.cl', '2026-04-10T10:00:00+00:00', 'c', '', '')
        """
    )
    conn.commit()
    conn.close()
    res = _run("--db", str(db), "--gmail-user", "contacto@origenlab.cl", "--out-dir", str(out))
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["overall"]["total_sent"] == 0


def test_export_email_conversation_intelligence_outputs(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    out = tmp_path / "out"
    _build_min_db(db)
    res = _run("--db", str(db), "--gmail-user", "contacto@origenlab.cl", "--out-dir", str(out))
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["overall"]["total_sent"] == 1
    assert payload["overall"]["total_received"] == 2
    assert payload["hot_opportunities"] >= 1

    report = out / "email_conversation_intelligence_report.md"
    real_csv = out / "real_client_conversations.csv"
    noise_csv = out / "noise_and_supplier_conversations.csv"
    assert report.is_file()
    assert real_csv.is_file()
    assert noise_csv.is_file()

    with real_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert list(rows[0].keys()) == LOCKED_REAL_CLIENT_COLUMNS
    assert any(r["contact_email"] == "ana@cliente.cl" for r in rows)
    ana = next(r for r in rows if r["contact_email"] == "ana@cliente.cl")
    assert int(ana["sent_count"]) >= 1
    assert int(ana["received_count"]) >= 1
    assert ana["status"] in {"hot_opportunity", "warm_opportunity", "needs_follow_up", "quoted_or_info_sent", "unknown"}

    with noise_csv.open(newline="", encoding="utf-8") as f:
        noise = list(csv.DictReader(f))
    assert any("admin_noise" in r["category"] for r in noise)
