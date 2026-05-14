"""Regression: suggested SQLite backup line must separate src and dest (quoted ``cp``)."""

from __future__ import annotations

import importlib.util
import shlex
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_dedupe_module():
    path = REPO / "scripts" / "maintenance" / "dedupe_canonical_gmail_messages.py"
    spec = importlib.util.spec_from_file_location("dedupe_cgm_mod", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_format_cp_sqlite_backup_command_splits_into_cp_src_dest() -> None:
    mod = _load_dedupe_module()
    cmd = mod.format_cp_sqlite_backup_command(Path("/tmp/example/emails.sqlite"), ts_utc="20260101T120000Z")
    parts = shlex.split(cmd, posix=True)
    assert parts[0] == "cp"
    assert len(parts) == 3
    assert parts[1] != parts[2]
    assert parts[1].endswith("emails.sqlite")
    assert ".backup-20260101T120000Z" in parts[2]


def test_format_cp_sqlite_backup_command_handles_spaces_in_path() -> None:
    mod = _load_dedupe_module()
    cmd = mod.format_cp_sqlite_backup_command(Path("/tmp/my vault/emails.sqlite"), ts_utc="20260101T120000Z")
    parts = shlex.split(cmd, posix=True)
    assert len(parts) == 3
    assert "my vault" in parts[1]
    assert parts[2].endswith("emails.sqlite.backup-20260101T120000Z")
