"""Integration tests for ``scripts/leads/mark_outreach_state.py``."""

from __future__ import annotations

import json
import os
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


def test_mark_outreach_state_missing_db_exits_1(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite"
    r = _run_cli(missing, "--email", "a@b.cl", "--state", "contacted", "--updated-by", "t")
    assert r.returncode == 1
    assert "not found" in r.stderr.lower() or "SQLite" in r.stderr


def test_mark_outreach_state_invalid_email_exits_2(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(db, "--email", "not-an-email", "--state", "contacted", "--updated-by", "t")
    assert r.returncode == 2
    assert "no válido" in r.stderr or "válido" in r.stderr


def test_mark_outreach_state_normalizes_email(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    r = _run_cli(
        db,
        "--email",
        "  Lead@CLIENTE.CL ",
        "--state",
        "contacted",
        "--updated-by",
        "pytest",
        "--source",
        "test_norm",
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
        "--email",
        "flow@cliente.cl",
        "--state",
        "contacted",
        "--updated-by",
        "op1",
        "--source",
        "s1",
    )
    assert r1.returncode == 0, r1.stderr + r1.stdout
    row1 = json.loads(r1.stdout)
    assert row1["state"] == "contacted"
    assert row1["first_contacted_at"] == row1["last_contacted_at"]
    first_ts = row1["first_contacted_at"]

    r2 = _run_cli(
        db,
        "--email",
        "flow@cliente.cl",
        "--state",
        "replied",
        "--updated-by",
        "op2",
        "--source",
        "s2",
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
        "--email",
        "flow@cliente.cl",
        "--state",
        "snoozed",
        "--updated-by",
        "op3",
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
        "--email",
        "flow@cliente.cl",
        "--state",
        "not_contacted",
        "--updated-by",
        "op4",
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
        "--batch-file",
        str(batch),
        "--state",
        "contacted",
        "--updated-by",
        "pytest_batch",
        "--source",
        "batch_test",
        "--notes",
        "sent",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    summary = json.loads(r.stdout)
    assert summary["ok"] is True
    assert summary["count"] == 2
    assert set(summary["emails"]) == {"a@x.cl", "b@y.cl"}


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
        "--lead-id",
        "1",
    )
    assert r.returncode == 2
