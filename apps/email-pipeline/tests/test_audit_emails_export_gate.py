"""CLI smoke tests for audit_emails_export_gate.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "audit_emails_export_gate.py"


def test_audit_emails_export_gate_empty_file_exits_2(tmp_path: Path) -> None:
    empty = tmp_path / "e.txt"
    empty.write_text("# only comment\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(empty)],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 2


def test_audit_emails_export_gate_one_email(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    db.write_bytes(b"")
    f = tmp_path / "one.txt"
    f.write_text("probe@cliente.cl\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(f), "--db", str(db)],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "audited=1" in r.stdout
