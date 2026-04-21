from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "mark_sent_batch_contacted.py"


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


def _read_state(db: Path, email: str) -> dict[str, object] | None:
    conn = sqlite3.connect(str(db))
    try:
        try:
            row = conn.execute(
                """
                SELECT contact_email_norm, state, first_contacted_at, last_contacted_at, source, notes, updated_by
                FROM outreach_contact_state WHERE contact_email_norm=?
                """,
                (email,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        cols = (
            "contact_email_norm",
            "state",
            "first_contacted_at",
            "last_contacted_at",
            "source",
            "notes",
            "updated_by",
        )
        return dict(zip(cols, row))
    finally:
        conn.close()


def test_source_required(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    f = tmp_path / "batch.txt"
    f.write_text("a@x.cl\n", encoding="utf-8")
    r = _run_cli(db, "--batch-file", str(f))
    assert r.returncode != 0
    assert "--source" in (r.stderr + r.stdout)


def test_parse_one_email_per_line_and_real_write(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    f = tmp_path / "batch.txt"
    f.write_text("a@x.cl\nb@y.cl\n", encoding="utf-8")
    r = _run_cli(
        db,
        "--batch-file",
        str(f),
        "--source",
        "manual_html_batch_1",
        "--updated-by",
        "pytest",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    payload = json.loads(r.stdout)
    assert payload["normalized_unique"] == 2
    assert payload["inserted"] == 2
    assert _read_state(db, "a@x.cl") is not None


def test_parse_csv_and_tsv(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    csv_f = tmp_path / "batch.csv"
    csv_f.write_text("contact_email,foo\none@x.cl,1\ntwo@y.cl,2\n", encoding="utf-8")
    tsv_f = tmp_path / "batch.tsv"
    tsv_f.write_text("email\tfoo\nthree@z.cl\t3\n", encoding="utf-8")
    r = _run_cli(
        db,
        "--batch-file",
        str(csv_f),
        "--batch-file",
        str(tsv_f),
        "--source",
        "manual_html_batch_2",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    payload = json.loads(r.stdout)
    assert payload["normalized_unique"] == 3


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    f = tmp_path / "batch.txt"
    f.write_text("a@x.cl\n", encoding="utf-8")
    r = _run_cli(db, "--batch-file", str(f), "--source", "manual_html_batch_3", "--dry-run")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["dry_run"] is True
    assert _read_state(db, "a@x.cl") is None


def test_second_run_preserves_first_and_updates_last(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    f = tmp_path / "batch.txt"
    f.write_text("a@x.cl\n", encoding="utf-8")
    r1 = _run_cli(db, "--batch-file", str(f), "--source", "batch_one")
    assert r1.returncode == 0
    first = _read_state(db, "a@x.cl")
    assert first and first["first_contacted_at"] == first["last_contacted_at"]
    r2 = _run_cli(db, "--batch-file", str(f), "--source", "batch_two")
    assert r2.returncode == 0
    second = _read_state(db, "a@x.cl")
    assert second
    assert second["first_contacted_at"] == first["first_contacted_at"]
    assert second["last_contacted_at"] != first["last_contacted_at"]
    p2 = json.loads(r2.stdout)
    assert p2["already_contacted"] == 1


def test_invalid_emails_skipped_and_empty_fails(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    bad = tmp_path / "bad.txt"
    bad.write_text("not-an-email\n#x\n", encoding="utf-8")
    r = _run_cli(db, "--batch-file", str(bad), "--source", "batch_bad")
    assert r.returncode == 2
    assert "No valid recipient emails" in r.stderr


def test_existing_not_contacted_becomes_contacted(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
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
    conn.execute(
        """
        INSERT INTO outreach_contact_state (
          contact_email_norm,state,first_contacted_at,last_contacted_at,source,notes,updated_at,updated_by,lead_id
        ) VALUES ('a@x.cl','not_contacted',NULL,NULL,'old','n','2026-01-01T00:00:00+00:00','u',NULL)
        """
    )
    conn.commit()
    conn.close()
    f = tmp_path / "batch.txt"
    f.write_text("a@x.cl\n", encoding="utf-8")
    r = _run_cli(db, "--batch-file", str(f), "--source", "batch_promote")
    assert r.returncode == 0, r.stderr + r.stdout
    row = _read_state(db, "a@x.cl")
    assert row and row["state"] == "contacted"
    p = json.loads(r.stdout)
    assert p["updated"] == 1


def test_send_manifest_input(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "results": [
                    {"real_to": "a@x.cl", "effective_to": "a@x.cl"},
                    {"real_to": "b@y.cl"},
                ]
            }
        ),
        encoding="utf-8",
    )
    r = _run_cli(db, "--send-manifest", str(manifest), "--source", "manifest_batch")
    assert r.returncode == 0, r.stderr + r.stdout
    p = json.loads(r.stdout)
    assert p["normalized_unique"] == 2

