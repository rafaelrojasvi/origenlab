"""Smoke test for read-only canonical source audit script."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "audit_canonical_contacto_gmail.py"


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            folder TEXT,
            message_id TEXT,
            date_iso TEXT,
            body TEXT,
            full_body_clean TEXT,
            top_reply_clean TEXT
        );
        CREATE TABLE attachments (id INTEGER PRIMARY KEY, email_id INTEGER);
        """
    )
    conn.executemany(
        "INSERT INTO emails VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "gmail:contacto@origenlab.cl/INBOX", "INBOX", "<a@x>", "2026-01-02T00:00:00Z", "b", "b", "b"),
            (
                2,
                "/mbox/contacto@labdelivery.cl/x/mbox",
                "Bandeja de entrada",
                "<b@x>",
                "2020-01-01T00:00:00Z",
                "",
                "",
                "",
            ),
            (3, "/other/backup/mbox", "Inbox", None, "", "", "", ""),
        ],
    )
    conn.execute("INSERT INTO attachments (id, email_id) VALUES (1, 1)")
    conn.commit()
    conn.close()


def test_audit_canonical_contacto_gmail_json(tmp_path: Path) -> None:
    db = tmp_path / "a.sqlite"
    _seed(db)
    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert cp.returncode == 0, cp.stderr + cp.stdout
    payload = json.loads(cp.stdout)
    assert payload["groups"]["A_canonical_gmail_contacto"]["row_count"] == 1
    assert payload["groups"]["B_legacy_labdelivery"]["row_count"] == 1
    assert payload["groups"]["C_other"]["row_count"] == 1
    assert payload["groups"]["A_canonical_gmail_contacto"]["attachments_linked"] == 1
