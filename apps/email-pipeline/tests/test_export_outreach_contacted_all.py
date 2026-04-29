from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "export_outreach_contacted_all.py"


def _run(db: Path, out: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), "--out", str(out), "--gmail-user", "contacto@origenlab.cl"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _seed_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE emails (
          recipients TEXT,
          source_file TEXT,
          folder TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO emails VALUES (?,?,?)",
        [
            ("To: A@x.cl", "gmail:contacto@origenlab.cl/m1", "[Gmail]/Enviados"),
            ("To: b@y.cl", "gmail:contacto@origenlab.cl/m2", "[Gmail]/Sent Mail"),
            ("To: B@Y.CL", "gmail:contacto@origenlab.cl/m3", "[Gmail]/Sent Mail"),
        ],
    )
    conn.executemany(
        "INSERT INTO outreach_contact_state VALUES (?,?)",
        [
            ("c@z.cl", "contacted"),
            ("d@w.cl", "replied"),
            ("e@v.cl", "snoozed"),
            ("f@u.cl", "not_contacted"),
            ("b@y.cl", "contacted"),
        ],
    )
    conn.commit()
    conn.close()


def test_export_outreach_contacted_all_union_and_header(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    out = tmp_path / "outreach_contacted_all.csv"
    _seed_db(db)
    cp = _run(db, out)
    assert cp.returncode == 0, cp.stderr + cp.stdout
    payload = json.loads(cp.stdout)
    assert payload["sent_unique_count"] == 2
    assert payload["outreach_state_blocking_count"] == 4
    assert payload["union_unique_count"] == 5
    assert payload["duplicates_removed"] == 1

    with out.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["contact_email"]
        rows = [r["contact_email"] for r in reader]
    assert rows == ["a@x.cl", "b@y.cl", "c@z.cl", "d@w.cl", "e@v.cl"]
