"""LIST response parsing for Gmail IMAP folder names."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _mod():
    root = Path(__file__).resolve().parents[1]
    p = root / "scripts" / "ingest" / "05_workspace_gmail_imap_to_sqlite.py"
    spec = importlib.util.spec_from_file_location("w05", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_mailbox_name_from_list_line_quoted() -> None:
    m = _mod()
    raw = br'(\HasNoChildren) "/" "[Gmail]/Sent Mail"'
    assert m._mailbox_name_from_list_line(raw) == "[Gmail]/Sent Mail"


def test_mailbox_name_from_list_line_inbox_atom() -> None:
    m = _mod()
    raw = br'(\HasNoChildren) "/" INBOX'
    assert m._mailbox_name_from_list_line(raw) == "INBOX"
