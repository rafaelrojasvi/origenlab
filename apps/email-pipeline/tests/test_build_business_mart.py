"""Regression tests for scripts/mart/build_business_mart.py."""

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


def test_build_business_mart_source_imports_counter() -> None:
    contact_org = REPO / "src" / "origenlab_email_pipeline" / "core" / "mart" / "contact_org_builder.py"
    text = contact_org.read_text(encoding="utf-8")
    assert "from collections import Counter" in text or "Counter, defaultdict" in text
    assert "doc_aggs.doc_counts_by_email.get(int(email_id), Counter())" in text


def test_build_business_mart_rebuild_limit_emails_no_name_error(tmp_path: Path) -> None:
    """Email scan uses Counter() default when doc_aggs has no row for an email_id."""
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from origenlab_email_pipeline.db import init_schema
    from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema

    init_schema(conn)
    migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART})
    conn.execute(
        """
        INSERT INTO emails (
          source_file, message_id, date_iso, folder, sender, recipients,
          subject, body, full_body_clean, top_reply_clean
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "gmail:contacto@origenlab.cl/INBOX",
            "msg-1",
            "2026-05-15T10:00:00",
            "INBOX",
            "Buyer <buyer@lab.cl>",
            "contacto@origenlab.cl",
            "Cotización equipos",
            "necesitamos cotización",
            "necesitamos cotización",
            "necesitamos cotización",
        ),
    )
    conn.commit()
    conn.close()

    env = {**os.environ, "PYTHONPATH": str(_SRC), "ORIGENLAB_SQLITE_PATH": str(db)}
    cp = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--rebuild",
            "--limit-emails",
            "5",
            "--internal-domain",
            "origenlab.cl",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert cp.returncode == 0, (cp.stdout + cp.stderr)[-4000:]
    assert "NameError" not in (cp.stdout + cp.stderr)

    conn2 = sqlite3.connect(db)
    contacts = conn2.execute("SELECT COUNT(*) FROM contact_master").fetchone()[0]
    orgs = conn2.execute("SELECT COUNT(*) FROM organization_master").fetchone()[0]
    signals = conn2.execute("SELECT COUNT(*) FROM opportunity_signals").fetchone()[0]
    conn2.close()
    assert contacts >= 0
    assert orgs >= 0
    assert signals >= 0
