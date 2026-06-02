"""NDR tooling parity: canonical flag_ndr vs ndr_bounce_extraction vs legacy reported-non-delivery."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_NDR_SCRIPT = REPO / "scripts/tools/flag_ndr_bounces_from_contacto.py"
_LEGACY_SCRIPT = REPO / "scripts/tools/flag_reported_non_delivery_from_contacto.py"


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ndr_script():
    return _load_script(_NDR_SCRIPT, "flag_ndr_bounces")


@pytest.fixture
def legacy_script():
    return _load_script(_LEGACY_SCRIPT, "flag_reported_ndr")


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


def test_legacy_does_not_flag_mailer_daemon_ndr(tmp_path: Path) -> None:
    """Legacy tool scans human senders only; DSN bounces are canonical NDR domain."""
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.reported_non_delivery_signals import text_suggests_reported_non_delivery

    body = _ndr_body("other@client.cl")
    conn = sqlite3.connect(tmp_path / "legacy.sqlite")
    _seed_contacto_emails(
        conn,
        [
            (
                "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                "Failure",
                body,
                "INBOX",
            ),
        ],
    )
    conn.close()
    assert not text_suggests_reported_non_delivery("Failure", body)


def test_legacy_flags_human_reported_non_delivery_not_ndr_scan(tmp_path: Path) -> None:
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


def test_legacy_unique_behavior_is_inbound_reply_heuristic() -> None:
    """Document: legacy path is complementary (inbound 'did not receive' text), not DSN parsing."""
    legacy = _LEGACY_SCRIPT.read_text(encoding="utf-8")
    ndr = _NDR_SCRIPT.read_text(encoding="utf-8")
    assert "reported_non_delivery" in legacy
    assert "text_suggests_reported_non_delivery" in legacy
    assert "reported_non_delivery" not in ndr
    assert "bounce_ndr" in ndr or "scan_ndr_planned_recipients" in ndr
