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
SCRIPT = REPO / "scripts" / "leads" / "process_broad_marketing_contacts.py"


def _run(db: Path, workspace: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--workspace",
            str(workspace),
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
            "To: buyer1@gate-test.example",
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
            "state1@gate-test.example",
            "replied",
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            "t",
            "",
            "2026-01-02T00:00:00Z",
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
        ("bad@gate-test.example", "manual_do_not_contact", None, None, None, "t", "t"),
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS supplier_import_batch (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_filename TEXT NOT NULL,
          file_sha256 TEXT NOT NULL,
          imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS supplier_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          domain_norm TEXT NOT NULL UNIQUE,
          trade_name TEXT,
          notes TEXT,
          is_exclusion INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS supplier_priority_snapshot (
          supplier_id INTEGER NOT NULL,
          batch_id INTEGER NOT NULL,
          tier TEXT NOT NULL,
          rank_in_list INTEGER NOT NULL,
          confidence_score REAL,
          confidence_label TEXT,
          category_context TEXT,
          PRIMARY KEY (supplier_id, batch_id)
        );
        CREATE TABLE IF NOT EXISTS contact_domain_suppression (
          domain_norm TEXT PRIMARY KEY,
          suppression_reason_text TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          updated_by TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO contact_domain_suppression VALUES (?,?,?,?)",
        ("blocked-domain.example", "test", "2026-01-01T00:00:00Z", "pytest"),
    )
    conn.commit()
    conn.close()


def _write_input(workspace: Path) -> None:
    text = """institution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal
Hosp Alpha,RM,Santiago,hospital,safe@official-gate.example,Director Compras,https://official-gate.example/contacto,high,licitaciones hospital
Hosp Beta,RM,Santiago,hospital,master@gate-test.example,Compras,https://beta-gate.example/,high,ok
Hosp Gamma,RM,Santiago,hospital,buyer1@gate-test.example,Compras,https://gamma-gate.example/,high,ok
Hosp Delta,RM,Santiago,hospital,state1@gate-test.example,Compras,https://delta-gate.example/,high,ok
Hosp Eps,RM,Santiago,hospital,bad@gate-test.example,Compras,https://eps-gate.example/,high,ok
Hosp Dup,RM,Santiago,hospital,dup@gate-test.example,Compras,https://dup-gate.example/,high,ok
Hosp Dup2,RM,Santiago,hospital,dup@gate-test.example,Compras,https://dup2-gate.example/,high,ok
Hosp Low,RM,Santiago,hospital,low@gate-test.example,Compras,https://low-gate.example/,low,ok
Hosp NoUrl,RM,Santiago,hospital,nourl@gate-test.example,Compras,,high,ok
Hosp Li,RM,Santiago,hospital,li@gate-test.example,Compras,https://www.linkedin.com/in/foo,medium,ok
Hosp Gen,RM,Santiago,hospital,gen@gate-test.example,contact,https://gen-gate.example/,high,
Hosp Dom,RM,Santiago,hospital,user@sub.blocked-domain.example,IT,https://dom-gate.example/,high,servers
"""
    (workspace / "reviewed_marketing_contacts.csv").write_text(text, encoding="utf-8")


def _write_master(workspace: Path) -> None:
    (workspace / "do_not_repeat_master.csv").write_text(
        "email_norm,source_kinds,source_count,first_seen_at,last_seen_at,notes\n"
        "master@gate-test.example,test,1,,,\n"
        "dup@gate-test.example,test,1,,,\n",
        encoding="utf-8",
    )


def test_processor_splits_and_send_ready(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_input(ws)
    _write_master(ws)
    r = _run(db, ws)
    assert r.returncode == 0, r.stderr + r.stdout

    summary = json.loads((ws / "marketing_contacts_summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["send_ready_marketing"] == 1

    with (ws / "send_ready_marketing.csv").open(encoding="utf-8", newline="") as f:
        send_rows = list(csv.DictReader(f))
    assert len(send_rows) == 1
    assert send_rows[0]["contact_email"] == "safe@official-gate.example"
    assert send_rows[0]["email_source"] == "marketing_contacts"
    assert send_rows[0]["case_id"] == "MKT-00001"

    with (ws / "marketing_blocked_already_known.csv").open(encoding="utf-8", newline="") as f:
        blocked = {row["contact_email"]: row["block_reason"] for row in csv.DictReader(f)}
    assert "master@gate-test.example" in blocked
    assert "dup@gate-test.example" in blocked
    assert "buyer1@gate-test.example" in blocked
    assert "state1@gate-test.example" in blocked
    assert "bad@gate-test.example" in blocked
    assert "dup@gate-test.example" in blocked
    assert "nourl@gate-test.example" in blocked
    assert "user@sub.blocked-domain.example" in blocked

    with (ws / "marketing_needs_manual_review.csv").open(encoding="utf-8", newline="") as f:
        review = {row["contact_email"]: row["review_reason"] for row in csv.DictReader(f)}
    assert "low@gate-test.example" in review
    assert "li@gate-test.example" in review
    assert "gen@gate-test.example" in review


def test_no_db_writes(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    h1 = hashlib.sha256(db.read_bytes()).hexdigest()
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_input(ws)
    _write_master(ws)
    r = _run(db, ws)
    assert r.returncode == 0, r.stderr + r.stdout
    h2 = hashlib.sha256(db.read_bytes()).hexdigest()
    assert h1 == h2


def test_summary_shape(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_input(ws)
    _write_master(ws)
    r = _run(db, ws)
    assert r.returncode == 0
    summary = json.loads((ws / "marketing_contacts_summary.json").read_text(encoding="utf-8"))
    for k in ("schema_version", "counts", "outputs", "gmail_user"):
        assert k in summary
