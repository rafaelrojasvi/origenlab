from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "export_do_not_repeat_master.py"


def _run(db: Path, active: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--reports-out-dir",
            str(active),
            "--out-dir",
            str(out),
            "--gmail-user",
            "contacto@origenlab.cl",
            "--sent-folder",
            "[Gmail]/Enviados",
            *extra,
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _seed_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE emails (
          recipients TEXT, source_file TEXT, folder TEXT, date_iso TEXT, date_raw TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?)",
        (
            "To: sent@cliente.cl",
            "gmail:contacto@origenlab.cl/m1",
            "[Gmail]/Enviados",
            "2026-04-01T10:00:00Z",
            "",
        ),
    )
    conn.execute(
        """CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY, state TEXT NOT NULL,
          first_contacted_at TEXT, last_contacted_at TEXT, source TEXT, notes TEXT,
          updated_at TEXT NOT NULL, updated_by TEXT, lead_id INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO outreach_contact_state VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "state@cliente.cl",
            "contacted",
            "2026-03-01T00:00:00Z",
            "2026-03-02T00:00:00Z",
            "t",
            "",
            "2026-03-02T00:00:00Z",
            "t",
            None,
        ),
    )
    conn.execute(
        """CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY, suppression_reason_code TEXT, suppression_reason_text TEXT,
          suppression_source TEXT, last_bounced_at TEXT, updated_at TEXT, updated_by TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO contact_email_suppression VALUES (?,?,?,?,?,?,?)",
        ("bad@x.cl", "manual_do_not_contact", None, None, None, "t", "t"),
    )
    conn.commit()
    conn.close()


def test_dedupes_sent_state_and_csv(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    active = tmp_path / "active"
    (active / "current").mkdir(parents=True)
    (active / "deepsearch_x.csv").write_text(
        "contact_email,foo\n"
        "csv@y.cl,1\n"
        "sent@cliente.cl,2\n",  # also in Sent
        encoding="utf-8",
    )
    out = active / "current"
    r = _run(db, active, out)
    assert r.returncode == 0, r.stderr + r.stdout
    with (out / "do_not_repeat_master.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by = {row["email_norm"]: row for row in rows}
    assert "sent@cliente.cl" in by
    assert "gmail_sent" in by["sent@cliente.cl"]["source_kinds"]
    assert "marketing_csv:deepsearch" in by["sent@cliente.cl"]["source_kinds"]
    assert int(by["sent@cliente.cl"]["source_count"]) >= 2
    assert "state@cliente.cl" in by
    assert "outreach_state" in by["state@cliente.cl"]["source_kinds"]
    assert "bad@x.cl" in by
    assert "email_suppression" in by["bad@x.cl"]["source_kinds"]
    summ = json.loads((out / "do_not_repeat_summary.json").read_text(encoding="utf-8"))
    assert summ["unique_emails"] == len(by)


def test_no_db_writes(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    h1 = hashlib.sha256(db.read_bytes()).hexdigest()
    active = tmp_path / "active"
    out = active / "current"
    out.mkdir(parents=True)
    r = _run(db, active, out)
    assert r.returncode == 0, r.stderr + r.stdout
    h2 = hashlib.sha256(db.read_bytes()).hexdigest()
    assert h1 == h2


def test_txt_lists_emails(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    active = tmp_path / "active"
    out = active / "current"
    out.mkdir(parents=True)
    r = _run(db, active, out)
    assert r.returncode == 0
    lines = (out / "do_not_repeat_master.txt").read_text(encoding="utf-8").splitlines()
    assert "sent@cliente.cl" in lines
