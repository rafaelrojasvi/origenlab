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
SCRIPT = REPO / "scripts" / "qa" / "export_outreach_volume_rollup.py"


def _run(
    db: Path,
    reports_out: Path,
    out_dir: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--reports-out-dir",
            str(reports_out),
            "--out-dir",
            str(out_dir),
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


def _read_rollup(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _seed_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE emails (
            recipients TEXT,
            source_file TEXT,
            folder TEXT,
            date_iso TEXT,
            date_raw TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?)",
        (
            "To: Alpha@Client.CL",
            "gmail:contacto@origenlab.cl/msg1",
            "[Gmail]/Enviados",
            "2026-04-01T10:00:00Z",
            "",
        ),
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?)",
        (
            "Cc: beta@client.cl",
            "gmail:contacto@origenlab.cl/msg2",
            "[Gmail]/Enviados",
            "2026-04-02T10:00:00Z",
            "",
        ),
    )
    conn.execute(
        """CREATE TABLE outreach_contact_state (
            contact_email_norm TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            first_contacted_at TEXT,
            last_contacted_at TEXT,
            source TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            lead_id INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO outreach_contact_state VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "alpha@client.cl",
            "contacted",
            None,
            "2026-04-01T12:00:00Z",
            "t",
            "",
            "2026-04-01T12:00:00Z",
            "t",
            None,
        ),
    )
    conn.execute(
        "INSERT INTO outreach_contact_state VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "gamma@other.cl",
            "replied",
            None,
            "2026-03-01T00:00:00Z",
            "t",
            "",
            "2026-03-01T00:00:00Z",
            "t",
            None,
        ),
    )
    conn.execute(
        "INSERT INTO outreach_contact_state VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "zzz@skip.cl",
            "not_contacted",
            None,
            None,
            "t",
            "",
            "2026-01-01T00:00:00Z",
            "t",
            None,
        ),
    )
    conn.commit()
    conn.close()


def test_rolls_up_gmail_and_state(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    active = tmp_path / "active"
    out_dir = active / "current"
    out_dir.mkdir(parents=True)
    run = _run(db, active, out_dir)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _read_rollup(out_dir / "outreach_volume_rollup.csv")
    by_kind = {r["source_kind"]: r for r in rows}
    assert by_kind["gmail_sent"]["unique_email_count"] == "2"
    assert by_kind["outreach_contact_state"]["unique_email_count"] == "2"
    assert by_kind["outreach_contact_state"]["row_count"] == "2"
    summary = json.loads((out_dir / "outreach_volume_summary.json").read_text(encoding="utf-8"))
    assert summary["totals"]["unique_sent_recipients_gmail"] == 2
    assert summary["totals"]["unique_contacted_state_emails"] == 2
    assert summary["totals"]["overlap_sent_and_contacted_state"] == 1


def test_csv_dedupes_case_insensitive(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    active = tmp_path / "active"
    marketing = active / "deepsearch_sample.csv"
    marketing.parent.mkdir(parents=True)
    marketing.write_text(
        "contact_email,org\n"
        "One@Hospital.CL, A\n"
        "ONE@hospital.cl, B\n"
        "not-an-email, C\n",
        encoding="utf-8",
    )
    out_dir = active / "current"
    out_dir.mkdir(parents=True)
    run = _run(db, active, out_dir)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _read_rollup(out_dir / "outreach_volume_rollup.csv")
    mrows = [r for r in rows if r["source_name"] == "deepsearch"]
    assert len(mrows) == 1
    assert mrows[0]["unique_email_count"] == "1"
    assert mrows[0]["row_count"] == "3"


def test_send_manifest_parsed(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    active = tmp_path / "active"
    batch = active / "batch_a"
    batch.mkdir(parents=True)
    (batch / "send_manifest.json").write_text(
        json.dumps(
            {
                "campaign_tag": "wave_1",
                "results": [{"real_to": "NEW1@x.cl"}, {"real_to": "NEW2@y.cl"}],
            }
        ),
        encoding="utf-8",
    )
    out_dir = active / "current"
    out_dir.mkdir(parents=True)
    run = _run(db, active, out_dir)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _read_rollup(out_dir / "outreach_volume_rollup.csv")
    mrows = [r for r in rows if r["source_kind"] == "send_manifest"]
    assert len(mrows) == 1
    assert mrows[0]["unique_email_count"] == "2"
    assert mrows[0]["campaign_tag"] == "wave_1"


def test_missing_reports_dir_ok(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    active = tmp_path / "nope"
    out_dir = tmp_path / "out"
    run = _run(db, active, out_dir)
    assert run.returncode == 0, run.stderr + run.stdout
    rows = _read_rollup(out_dir / "outreach_volume_rollup.csv")
    assert len(rows) == 2


def test_no_db_writes(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    h1 = hashlib.sha256(db.read_bytes()).hexdigest()
    active = tmp_path / "active"
    (active / "current").mkdir(parents=True)
    run = _run(db, active, active / "current")
    assert run.returncode == 0, run.stderr + run.stdout
    h2 = hashlib.sha256(db.read_bytes()).hexdigest()
    assert h1 == h2


def test_db_missing_returns_error(tmp_path: Path) -> None:
    db = tmp_path / "missing.sqlite"
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--reports-out-dir",
            str(tmp_path / "a"),
            "--out-dir",
            str(tmp_path / "o"),
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 1
    assert "not found" in r.stderr.lower()
