"""Gmail Workspace IMAP ingest helpers — Phase 2/3 locks on origenlab_email_pipeline.ingest.gmail_imap."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_SCRIPT = REPO / "scripts" / "ingest" / "05_workspace_gmail_imap_to_sqlite.py"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.ingest import gmail_imap


def _script_mod():
    spec = importlib.util.spec_from_file_location("w05_ingest", _SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_source_label_format() -> None:
    assert gmail_imap.source_label("contacto@origenlab.cl", "INBOX") == "gmail:contacto@origenlab.cl/INBOX"


def test_imap_select_folder_quotes_non_simple_mailbox() -> None:
    mail = MagicMock()
    mail._quote.return_value = '"[Gmail]/Sent Mail"'
    mail.select.return_value = ("OK", None)
    typ, _ = gmail_imap.imap_select_folder(mail, "[Gmail]/Sent Mail", readonly=True)
    assert typ == "OK"
    mail._quote.assert_called_once_with("[Gmail]/Sent Mail")
    mail.select.assert_called_once_with('"[Gmail]/Sent Mail"', readonly=True)


def test_imap_select_folder_simple_mailbox_no_quote() -> None:
    mail = MagicMock()
    mail.select.return_value = ("OK", None)
    typ, _ = gmail_imap.imap_select_folder(mail, "INBOX", readonly=True)
    assert typ == "OK"
    mail.select.assert_called_once_with("INBOX", readonly=True)
    mail._quote.assert_not_called()


def test_search_uids_since_days() -> None:
    mail = MagicMock()
    mail.uid.return_value = ("OK", [b"1 2 3"])
    uids = gmail_imap.search_uids(mail, since_days=7)
    assert uids == [b"1", b"2", b"3"]
    assert mail.uid.call_args[0][2] == "SINCE"


def test_replace_source_deletes_only_matching_source_file(tmp_path: Path) -> None:
    """Lock break-glass semantics: DELETE scoped to one gmail: user/folder source_file."""
    from origenlab_email_pipeline.db import connect, init_schema, insert_email

    db = tmp_path / "emails.sqlite"
    conn = connect(db)
    init_schema(conn)
    insert_email(
        conn,
        source_file="gmail:user@x.cl/INBOX",
        folder="INBOX",
        message_id="<a@x>",
        subject="a",
        sender="a@x",
        recipients="b@y",
        date_raw=None,
        date_iso="2026-06-01T00:00:00Z",
        body="",
        body_html=None,
        body_text_raw="",
        body_text_clean="",
        body_source_type="plain",
        body_has_plain=1,
        body_has_html=0,
        full_body_clean="",
        top_reply_clean="",
        attachment_count=0,
        has_attachments=0,
    )
    insert_email(
        conn,
        source_file="gmail:user@x.cl/[Gmail]/Sent Mail",
        folder="Sent",
        message_id="<b@x>",
        subject="b",
        sender="user@x.cl",
        recipients="c@z",
        date_raw=None,
        date_iso="2026-06-02T00:00:00Z",
        body="",
        body_html=None,
        body_text_raw="",
        body_text_clean="",
        body_source_type="plain",
        body_has_plain=1,
        body_has_html=0,
        full_body_clean="",
        top_reply_clean="",
        attachment_count=0,
        has_attachments=0,
    )
    conn.commit()
    source_inbox = "gmail:user@x.cl/INBOX"
    gmail_imap.delete_emails_for_source_file(conn, source_inbox)
    rows = conn.execute("SELECT source_file FROM emails ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["gmail:user@x.cl/[Gmail]/Sent Mail"]


def test_skip_duplicate_message_id_logic(tmp_path: Path) -> None:
    from origenlab_email_pipeline.db import connect, init_schema, insert_email

    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_schema(conn)
    insert_email(
        conn,
        source_file="gmail:u/f",
        folder="INBOX",
        message_id="<dup@t>",
        subject="s",
        sender="a@b",
        recipients="c@d",
        date_raw=None,
        date_iso=None,
        body="",
        body_html=None,
        body_text_raw="",
        body_text_clean="",
        body_source_type="plain",
        body_has_plain=1,
        body_has_html=0,
        full_body_clean="",
        top_reply_clean="",
        attachment_count=0,
        has_attachments=0,
    )
    conn.commit()
    existing = gmail_imap.load_existing_message_ids(conn)
    assert "<dup@t>" in existing
    conn.close()


@pytest.fixture
def oauth_env(tmp_path: Path) -> dict[str, str]:
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}), encoding="utf-8")
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    db = tmp_path / "ingest.sqlite"
    return {
        "ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON": str(client),
        "ORIGENLAB_GMAIL_TOKEN_JSON": str(token),
        "ORIGENLAB_GMAIL_WORKSPACE_USER": "contacto@origenlab.cl",
        "ORIGENLAB_SQLITE_PATH": str(db),
        "PYTHONPATH": str(_SRC),
    }


def test_mocked_ingest_inserts_email_and_skips_duplicate(
    tmp_path: Path, oauth_env: dict[str, str]
) -> None:
    pytest.importorskip("google.auth")
    raw = (
        b"From: Writer <writer@client.test>\r\n"
        b"To: contacto@origenlab.cl\r\n"
        b"Subject: Unit ingest\r\n"
        b"Message-ID: <phase2-ingest@origenlab.test>\r\n"
        b"\r\n"
        b"Body text.\r\n"
    )
    uid = b"42"

    class FakeMail:
        def uid(self, cmd, *args):
            if cmd == "SEARCH":
                return "OK", [uid]
            if cmd == "FETCH":
                return "OK", [(b"meta", raw)]
            return "NO", None

        def select(self, *a, **k):
            return "OK", None

        def logout(self):
            return "OK", None

        def _quote(self, s):
            return f'"{s}"'

    creds = MagicMock()
    creds.token = "fake-token"

    env = {**os.environ, **oauth_env}
    m = _script_mod()
    oauth_patch = "origenlab_email_pipeline.gmail_workspace_oauth"
    with (
        patch.dict(os.environ, env, clear=False),
        patch(f"{oauth_patch}.load_credentials_for_gmail_imap", return_value=creds),
        patch(f"{oauth_patch}.xoauth2_authenticate"),
        patch("imaplib.IMAP4_SSL", return_value=FakeMail()),
    ):
        rc1 = m.main()
    assert rc1 == 0

    db = Path(oauth_env["ORIGENLAB_SQLITE_PATH"])
    conn = sqlite3.connect(db)
    n1 = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    assert n1 == 1
    conn.close()

    with (
        patch.dict(os.environ, env, clear=False),
        patch(f"{oauth_patch}.load_credentials_for_gmail_imap", return_value=creds),
        patch(f"{oauth_patch}.xoauth2_authenticate"),
        patch("imaplib.IMAP4_SSL", return_value=FakeMail()),
        patch.object(
            sys,
            "argv",
            [
                "05_workspace_gmail_imap_to_sqlite.py",
                "--folder",
                "INBOX",
                "--skip-duplicate-message-id",
            ],
        ),
    ):
        rc2 = m.main()
    assert rc2 == 0
    conn = sqlite3.connect(db)
    n2 = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    assert n2 == 1


def test_ingest_parsed_message_to_sqlite_with_attachment(tmp_path: Path) -> None:
    from origenlab_email_pipeline.db import connect, init_schema

    raw = (
        b"From: a@client.test\r\n"
        b"To: contacto@origenlab.cl\r\n"
        b"Subject: Attach\r\n"
        b"Message-ID: <attach-phase2@test>\r\n"
        b'Content-Type: multipart/mixed; boundary="b"\r\n'
        b"\r\n"
        b"--b\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Hello\r\n"
        b"--b--\r\n"
    )
    msg = gmail_imap.message_from_bytes(raw)
    conn = connect(tmp_path / "t.sqlite")
    init_schema(conn)
    existing: set[str] = set()
    outcome, _ = gmail_imap.ingest_parsed_message_to_sqlite(
        conn,
        msg,
        source_file="gmail:contacto@origenlab.cl/INBOX",
        folder="INBOX",
        existing_mids=existing,
        skip_duplicate_message_id=False,
    )
    conn.commit()
    row = conn.execute("SELECT subject, source_file FROM emails LIMIT 1").fetchone()
    conn.close()
    assert outcome == "inserted"
    assert row is not None
    assert "Attach" in (row[0] or "")
