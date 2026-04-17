"""CLI smoke: import_operator_outreach_blocklist upserts email + domain suppressions."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "import_operator_outreach_blocklist.py"


@pytest.mark.skipif(not SCRIPT.is_file(), reason="import script missing")
def test_import_operator_outreach_blocklist_smoke(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    emails = tmp_path / "em.txt"
    emails.write_text("blockme-smoke@unique-block.example\n", encoding="utf-8")
    domains = tmp_path / "dom.txt"
    domains.write_text("unique-domain-block.example\n", encoding="utf-8")

    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--emails-file",
            str(emails),
            "--domains-file",
            str(domains),
            "--updated-by",
            "pytest",
        ],
        cwd=str(REPO),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout

    conn = sqlite3.connect(str(db))
    try:
        n_e = conn.execute("SELECT COUNT(*) FROM contact_email_suppression").fetchone()[0]
        n_d = conn.execute("SELECT COUNT(*) FROM contact_domain_suppression").fetchone()[0]
        assert n_e == 1
        assert n_d == 1
        em = conn.execute(
            "SELECT email FROM contact_email_suppression LIMIT 1"
        ).fetchone()[0]
        assert em == "blockme-smoke@unique-block.example"
    finally:
        conn.close()
