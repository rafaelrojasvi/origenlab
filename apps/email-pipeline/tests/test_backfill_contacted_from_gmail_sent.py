from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "backfill_contacted_from_gmail_sent.py"


def _run_cli(db: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), *extra],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _json_from_stdout(text: str) -> dict[str, object]:
    start = text.find("{")
    assert start >= 0, text
    return json.loads(text[start:])


def _seed_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE emails (
          recipients TEXT,
          source_file TEXT,
          folder TEXT,
          date_iso TEXT,
          date_raw TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          first_contacted_at TEXT,
          last_contacted_at TEXT,
          source TEXT,
          notes TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT,
          lead_id INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO emails VALUES (?,?,?,?,?)",
        [
            (
                "To: A@X.CL, b@y.cl",
                "gmail:contacto@origenlab.cl/m1",
                "[Gmail]/Enviados",
                "2026-04-01T10:00:00Z",
                "",
            ),
            (
                "to: a@x.cl",
                "gmail:contacto@origenlab.cl/m2",
                "[Gmail]/Sent Mail",
                "2026-04-02T11:00:00Z",
                "",
            ),
            (
                "to: person@origenlab.cl",
                "gmail:contacto@origenlab.cl/m3",
                "[Gmail]/Enviados",
                "2026-04-03T11:00:00Z",
                "",
            ),
        ],
    )
    conn.execute(
        """
        INSERT INTO outreach_contact_state (
          contact_email_norm,state,first_contacted_at,last_contacted_at,source,notes,updated_at,updated_by,lead_id
        ) VALUES ('b@y.cl','contacted','2026-01-01T00:00:00Z','2026-01-02T00:00:00Z','old','n','2026-01-02T00:00:00Z','u',NULL)
        """
    )
    conn.commit()
    conn.close()


def _read_state_row(db: Path, email: str) -> tuple | None:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            """
            SELECT contact_email_norm,state,first_contacted_at,last_contacted_at,source,notes,updated_by
            FROM outreach_contact_state WHERE contact_email_norm=?
            """,
            (email,),
        ).fetchone()
        return row
    finally:
        conn.close()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    r = _run_cli(
        db,
        "--gmail-user",
        "contacto@origenlab.cl",
        "--sent-folder",
        "[Gmail]/Enviados",
        "--sent-folder",
        "[Gmail]/Sent Mail",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    p = _json_from_stdout(r.stdout)
    assert p["dry_run"] is True
    assert p["would_insert"] == 1
    assert _read_state_row(db, "a@x.cl") is None


def test_apply_inserts_missing_sent_recipients(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    r = _run_cli(
        db,
        "--gmail-user",
        "contacto@origenlab.cl",
        "--sent-folder",
        "[Gmail]/Enviados",
        "--sent-folder",
        "[Gmail]/Sent Mail",
        "--apply",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    p = json.loads(r.stdout)
    assert p["applied_inserts"] == 1
    row = _read_state_row(db, "a@x.cl")
    assert row is not None
    assert row[1] == "contacted"


def test_existing_state_rows_not_overwritten(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    before = _read_state_row(db, "b@y.cl")
    assert before is not None
    r = _run_cli(
        db,
        "--gmail-user",
        "contacto@origenlab.cl",
        "--sent-folder",
        "[Gmail]/Enviados",
        "--sent-folder",
        "[Gmail]/Sent Mail",
        "--apply",
    )
    assert r.returncode == 0
    after = _read_state_row(db, "b@y.cl")
    assert after == before


def test_earliest_latest_sent_dates_used(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    r = _run_cli(
        db,
        "--gmail-user",
        "contacto@origenlab.cl",
        "--sent-folder",
        "[Gmail]/Enviados",
        "--sent-folder",
        "[Gmail]/Sent Mail",
        "--apply",
    )
    assert r.returncode == 0
    row = _read_state_row(db, "a@x.cl")
    assert row is not None
    assert row[2] == "2026-04-01T10:00:00Z"
    assert row[3] == "2026-04-02T11:00:00Z"


def test_internal_domain_skipped(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    r = _run_cli(
        db,
        "--gmail-user",
        "contacto@origenlab.cl",
        "--sent-folder",
        "[Gmail]/Enviados",
        "--sent-folder",
        "[Gmail]/Sent Mail",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    p = _json_from_stdout(r.stdout)
    assert p["skipped_internal"] >= 1
    assert _read_state_row(db, "person@origenlab.cl") is None


def test_json_shape_stable_with_json_out(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    _seed_db(db)
    out = tmp_path / "report.json"
    r = _run_cli(
        db,
        "--gmail-user",
        "contacto@origenlab.cl",
        "--sent-folder",
        "[Gmail]/Enviados",
        "--sent-folder",
        "[Gmail]/Sent Mail",
        "--json-out",
        str(out),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    expected_keys = {
        "ok",
        "dry_run",
        "db_path",
        "gmail_user",
        "sent_folders",
        "source",
        "updated_by",
        "limit",
        "sent_email_rows_scanned",
        "sent_unique",
        "existing_state",
        "missing_state",
        "would_insert",
        "skipped_existing",
        "skipped_invalid",
        "skipped_internal",
        "applied_inserts",
        "applied_updates",
        "sample_backfill_emails",
    }
    assert expected_keys.issubset(payload.keys())
