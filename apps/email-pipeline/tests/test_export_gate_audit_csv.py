from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "export_gate_audit_csv.py"


def _run(db: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--out", str(out), *extra],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _seed(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT,
          email_norm TEXT,
          org_name TEXT,
          domain_norm TEXT,
          fit_bucket TEXT,
          upstream_sync_state TEXT,
          last_seen_at TEXT
        );
        CREATE TABLE emails (
          recipients TEXT,
          source_file TEXT,
          folder TEXT
        );
        CREATE TABLE contact_email_suppression (email TEXT PRIMARY KEY, suppression_reason_code TEXT);
        CREATE TABLE contact_domain_suppression (domain_norm TEXT PRIMARY KEY, suppression_reason_text TEXT, updated_at TEXT, updated_by TEXT);
        CREATE TABLE outreach_contact_state (contact_email_norm TEXT PRIMARY KEY, state TEXT);
        """
    )
    conn.executemany(
        """
        INSERT INTO lead_master (email,email_norm,org_name,domain_norm,fit_bucket,upstream_sync_state,last_seen_at)
        VALUES (?,?,?,?,?,'active','2026-04-21T00:00:00+00:00')
        """,
        [
            ("sent@example.com", "sent@example.com", "Sent Org", "example.com", "high_fit"),
            ("state@example.com", "state@example.com", "State Org", "example.com", "high_fit"),
            ("supp@example.com", "supp@example.com", "Supp Org", "example.com", "high_fit"),
            ("ok@good.com", "ok@good.com", "Good Org", "good.com", "high_fit"),
        ],
    )
    conn.execute(
        """
        INSERT INTO emails (recipients, source_file, folder)
        VALUES ('sent@example.com', 'gmail:contacto@origenlab.cl/x', '[Gmail]/Enviados')
        """
    )
    conn.execute(
        "INSERT INTO outreach_contact_state (contact_email_norm, state) VALUES ('state@example.com', 'contacted')"
    )
    conn.execute(
        "INSERT INTO contact_email_suppression (email, suppression_reason_code) VALUES ('supp@example.com', 'manual_do_not_contact')"
    )
    conn.commit()
    conn.close()


def test_export_gate_audit_csv_lead_flags_and_columns(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--limit", "100", "--lane", "lead")
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    assert rows
    assert list(rows[0].keys()) == [
        "email",
        "lead_id",
        "organization_name",
        "organization_domain",
        "fit_bucket",
        "blocked_by_sent",
        "blocked_by_outreach_state",
        "outreach_state",
        "blocked_by_email_suppression",
        "blocked_by_domain_suppression",
        "blocked_by_internal_domain",
        "blocked_by_invalid_email",
        "final_eligible",
        "exclusion_reason",
    ]
    by_email = {r["email"]: r for r in rows}
    assert by_email["sent@example.com"]["blocked_by_sent"] == "1"
    assert by_email["state@example.com"]["blocked_by_outreach_state"] == "1"
    assert by_email["state@example.com"]["outreach_state"] == "contacted"
    assert by_email["supp@example.com"]["blocked_by_email_suppression"] == "1"
    assert by_email["ok@good.com"]["final_eligible"] == "1"


def test_export_gate_audit_csv_eligible_only(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "audit.csv"
    _seed(db)
    run = _run(db, out, "--lane", "lead", "--eligible-only")
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _rows(out)
    assert rows
    assert all(r["final_eligible"] == "1" for r in rows)
    assert all(r["exclusion_reason"] == "" for r in rows)

