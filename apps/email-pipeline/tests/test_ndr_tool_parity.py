"""NDR tooling parity: canonical flag_ndr vs ndr_bounce_extraction."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_NDR_SCRIPT = REPO / "scripts/tools/flag_ndr_bounces_from_contacto.py"


def _ndr_body(recipient: str = "failed@client.cl") -> str:
    return f"""
Final-Recipient: rfc822; {recipient}
Diagnostic-Code: smtp; 550 5.1.1 User unknown
Subject: Delivery Status Notification (Failure)
"""


def _reported_non_delivery_body() -> str:
    return "Hola, no recibimos su correo anterior. Por favor reenviar la cotizacion."


def _seed_contacto_emails(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.db import init_schema

    init_schema(conn)
    for sender, subject, body, folder in rows:
        conn.execute(
            """
            INSERT INTO emails (
              source_file, folder, sender, subject,
              full_body_clean, body_text_clean, body, date_iso
            ) VALUES (
              'gmail:contacto@origenlab.cl/INBOX', ?, ?, ?,
              ?, ?, ?, '2026-06-01T10:00:00Z'
            )
            """,
            (folder, sender, subject, body, body, body),
        )
    conn.commit()


def test_flag_ndr_script_uses_ndr_contacto_scan(tmp_path: Path) -> None:
    text = _NDR_SCRIPT.read_text(encoding="utf-8")
    assert "scan_ndr_planned_recipients" in text
    assert "ndr_contacto_scan" in text
    assert "ndr_bounce_extraction" not in text  # extraction via scan module


def test_scan_ndr_uses_bounce_extraction_on_dsn_body(tmp_path: Path) -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.email_business_filters import classify_email
    from origenlab_email_pipeline.ndr_bounce_extraction import (
        bounce_suppression_code_from_ndr_text,
        extract_failed_recipients_from_ndr,
    )
    from origenlab_email_pipeline.ndr_contacto_scan import scan_ndr_planned_recipients

    body = _ndr_body("parity@hospital.cl")
    conn = sqlite3.connect(tmp_path / "ndr.sqlite")
    _seed_contacto_emails(
        conn,
        [
            (
                "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                "Delivery Status Notification (Failure)",
                body,
                "INBOX",
            ),
        ],
    )
    planned, scanned, skipped = scan_ndr_planned_recipients(conn, since_days=None, limit=100)
    conn.close()
    assert scanned >= 1
    assert "parity@hospital.cl" in planned
    assert planned["parity@hospital.cl"][0] == bounce_suppression_code_from_ndr_text(body)
    assert extract_failed_recipients_from_ndr(body) == ["parity@hospital.cl"]
    cl = classify_email(sender="mailer-daemon@googlemail.com", subject="Failure", body=body)
    assert "bounce_ndr" in cl.get("tags", [])


def test_reported_signal_does_not_match_mailer_daemon_body(tmp_path: Path) -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.reported_non_delivery_signals import text_suggests_reported_non_delivery

    body = _ndr_body("other@client.cl")
    assert not text_suggests_reported_non_delivery("Failure", body)


def test_human_reported_detected_by_canonical_scan_not_ndr(tmp_path: Path) -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.ndr_contacto_scan import scan_ndr_planned_recipients
    from origenlab_email_pipeline.reported_non_delivery_signals import text_suggests_reported_non_delivery

    body = _reported_non_delivery_body()
    conn = sqlite3.connect(tmp_path / "human.sqlite")
    _seed_contacto_emails(
        conn,
        [
            (
                "Comprador <comprador@institucion.cl>",
                "No recibimos su mail",
                body,
                "INBOX",
            ),
        ],
    )
    planned, _, _ = scan_ndr_planned_recipients(conn, since_days=None, limit=50)
    conn.close()
    assert text_suggests_reported_non_delivery("No recibimos su mail", body)
    assert "comprador@institucion.cl" not in planned


def test_canonical_script_supports_include_reported_non_delivery_flag() -> None:
    text = _NDR_SCRIPT.read_text(encoding="utf-8")
    assert "--include-reported-non-delivery" in text
    assert "scan_reported_non_delivery_senders" in text
    assert "human_reported_non_delivery" in text


def test_canonical_default_scan_ndr_only(tmp_path: Path) -> None:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.ndr_contacto_scan import scan_ndr_planned_recipients
    from origenlab_email_pipeline.reported_non_delivery_contacto_scan import (
        scan_reported_non_delivery_senders,
    )

    body = _reported_non_delivery_body()
    conn = sqlite3.connect(tmp_path / "default.sqlite")
    _seed_contacto_emails(
        conn,
        [
            (
                "Comprador <comprador@institucion.cl>",
                "No recibimos su mail",
                body,
                "INBOX",
            ),
        ],
    )
    planned_ndr, _, _ = scan_ndr_planned_recipients(conn, since_days=None, limit=50)
    reported, _ = scan_reported_non_delivery_senders(conn, since_days=None, limit=50)
    conn.close()
    assert "comprador@institucion.cl" not in planned_ndr
    assert "comprador@institucion.cl" in reported


def test_canonical_cli_dry_run_labels_human_reported_non_delivery(tmp_path: Path) -> None:
    import os
    import subprocess

    db = tmp_path / "human_cli.sqlite"
    conn = sqlite3.connect(db)
    _seed_contacto_emails(
        conn,
        [
            (
                "Comprador <comprador@institucion.cl>",
                "No recibimos su mail",
                _reported_non_delivery_body(),
                "INBOX",
            ),
        ],
    )
    conn.close()

    r = subprocess.run(
        [
            sys.executable,
            str(_NDR_SCRIPT),
            "--db",
            str(db),
            "--include-reported-non-delivery",
            "--limit",
            "100",
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "human_reported_non_delivery" in r.stdout
    assert "comprador@institucion.cl" in r.stdout
    assert "Dry run only" in r.stdout
    assert "bounce_ndr with extracted recipient: 0" in r.stdout
