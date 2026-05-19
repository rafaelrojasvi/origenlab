"""Integration tests for ``scripts/leads/mark_outreach_state.py``."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/leads/mark_outreach_state.py"


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


def _count_state(db: Path, email: str) -> int:
    conn = sqlite3.connect(db)
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM outreach_contact_state WHERE contact_email_norm = ?",
            (email.lower().strip(),),
        )
        return int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def test_mark_outreach_state_help_exits_zero() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "not_contacted" in r.stdout
    assert "block" in r.stdout.lower() or "Blocking" in r.stdout
    assert "dry-run" in r.stdout.lower() or "Dry-run" in r.stdout
    assert "--apply" in r.stdout


def test_mark_outreach_state_missing_db_exits_1(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite"
    r = _run_cli(
        missing,
        "--email",
        "a@b.cl",
        "--state",
        "contacted",
        "--updated-by",
        "t",
        "--source",
        "s",
        "--reason",
        "test",
    )
    assert r.returncode == 1
    assert "not found" in r.stderr.lower() or "SQLite" in r.stderr


def test_mark_outreach_state_invalid_email_exits_2(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(
        db,
        "--email",
        "not-an-email",
        "--state",
        "contacted",
        "--updated-by",
        "t",
        "--source",
        "s",
        "--reason",
        "test",
    )
    assert r.returncode == 2
    assert "no válido" in r.stderr or "válido" in r.stderr


def test_mark_outreach_state_default_dry_run_does_not_write(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(
        db,
        "--email",
        "dry@cliente.cl",
        "--state",
        "contacted",
        "--updated-by",
        "pytest",
        "--source",
        "dry_run_test",
        "--reason",
        "preview only",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    preview = json.loads(r.stdout)
    assert preview["dry_run"] is True
    assert preview["contact_email_norm"] == "dry@cliente.cl"
    assert preview["new_state"] == "contacted"
    assert preview["old_state"] is None
    assert preview["source"] == "dry_run_test"
    assert preview["updated_by"] == "pytest"
    assert preview["reason"] == "preview only"
    assert _count_state(db, "dry@cliente.cl") == 0


def test_mark_outreach_state_apply_without_audit_fields_fails(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(
        db,
        "--apply",
        "--email",
        "a@b.cl",
        "--state",
        "contacted",
    )
    assert r.returncode == 2
    assert "ERROR:" in r.stderr
    assert _count_state(db, "a@b.cl") == 0


def test_mark_outreach_state_operator_and_source_artifact_aliases(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(
        db,
        "--apply",
        "--email",
        "alias@cliente.cl",
        "--state",
        "contacted",
        "--operator",
        "pytest_op",
        "--source-artifact",
        "artifact_slug",
        "--reason",
        "alias fields",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    row = json.loads(r.stdout)
    assert row["contact_email_norm"] == "alias@cliente.cl"
    assert row["updated_by"] == "pytest_op"
    assert row["source"] == "artifact_slug"


def test_mark_outreach_state_normalizes_email(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(
        db,
        "--apply",
        "--email",
        "  Lead@CLIENTE.CL ",
        "--state",
        "contacted",
        "--updated-by",
        "pytest",
        "--source",
        "test_norm",
        "--reason",
        "normalize",
        "--notes",
        "n",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    row = json.loads(r.stdout)
    assert row["contact_email_norm"] == "lead@cliente.cl"
    assert row["state"] == "contacted"


def test_mark_outreach_state_lifecycle(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")

    r1 = _run_cli(
        db,
        "--apply",
        "--email",
        "flow@cliente.cl",
        "--state",
        "contacted",
        "--updated-by",
        "op1",
        "--source",
        "s1",
        "--reason",
        "first touch",
    )
    assert r1.returncode == 0, r1.stderr + r1.stdout
    row1 = json.loads(r1.stdout)
    assert row1["state"] == "contacted"
    assert row1["first_contacted_at"] == row1["last_contacted_at"]
    first_ts = row1["first_contacted_at"]

    r2 = _run_cli(
        db,
        "--apply",
        "--email",
        "flow@cliente.cl",
        "--state",
        "replied",
        "--updated-by",
        "op2",
        "--source",
        "s2",
        "--reason",
        "got reply",
    )
    assert r2.returncode == 0, r2.stderr + r2.stdout
    row2 = json.loads(r2.stdout)
    assert row2["state"] == "replied"
    assert row2["first_contacted_at"] == first_ts
    assert row2["last_contacted_at"] is not None
    assert row2["updated_by"] == "op2"
    assert row2["source"] == "s2"

    r3 = _run_cli(
        db,
        "--apply",
        "--email",
        "flow@cliente.cl",
        "--state",
        "snoozed",
        "--updated-by",
        "op3",
        "--source",
        "s3",
        "--reason",
        "snooze",
        "--notes",
        "later",
    )
    assert r3.returncode == 0, r3.stderr + r3.stdout
    row3 = json.loads(r3.stdout)
    assert row3["state"] == "snoozed"
    assert row3["first_contacted_at"] == first_ts
    assert row3["notes"] == "later"

    r4 = _run_cli(
        db,
        "--apply",
        "--email",
        "flow@cliente.cl",
        "--state",
        "not_contacted",
        "--updated-by",
        "op4",
        "--source",
        "reset",
        "--reason",
        "clear memory",
    )
    assert r4.returncode == 0, r4.stderr + r4.stdout
    row4 = json.loads(r4.stdout)
    assert row4["state"] == "not_contacted"
    assert row4["first_contacted_at"] is None
    assert row4["last_contacted_at"] is None


def test_mark_outreach_state_batch_file(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    batch = tmp_path / "emails.txt"
    batch.write_text(
        "# header\n"
        "arch_001\ta@x.cl\textra\n"
        "b@y.cl\n"
        "b@y.cl\n",  # duplicate ignored
        encoding="utf-8",
    )
    r = _run_cli(
        db,
        "--apply",
        "--batch-file",
        str(batch),
        "--state",
        "contacted",
        "--updated-by",
        "pytest_batch",
        "--source",
        "batch_test",
        "--reason",
        "batch mark",
        "--notes",
        "sent",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    summary = json.loads(r.stdout)
    assert summary["ok"] is True
    assert summary["applied"] is True
    assert summary["count"] == 2
    assert set(summary["emails"]) == {"a@x.cl", "b@y.cl"}


def test_mark_outreach_state_batch_dry_run(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    batch = tmp_path / "emails.txt"
    batch.write_text("a@x.cl\n", encoding="utf-8")
    r = _run_cli(
        db,
        "--batch-file",
        str(batch),
        "--state",
        "contacted",
        "--updated-by",
        "pytest",
        "--source",
        "batch_dry",
        "--reason",
        "preview batch",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    summary = json.loads(r.stdout)
    assert summary["dry_run"] is True
    assert summary["count"] == 1
    assert _count_state(db, "a@x.cl") == 0


def test_mark_outreach_state_batch_rejects_lead_id(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    batch = tmp_path / "e.txt"
    batch.write_text("a@z.cl\n", encoding="utf-8")
    r = _run_cli(
        db,
        "--batch-file",
        str(batch),
        "--state",
        "contacted",
        "--updated-by",
        "t",
        "--source",
        "s",
        "--reason",
        "x",
        "--lead-id",
        "1",
    )
    assert r.returncode == 2
