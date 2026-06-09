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


def test_log_gmail_ingest_phases_emits_all_lines(capsys) -> None:
    timings = gmail_imap.GmailIngestPhaseTimings(
        auth_seconds=1.1,
        connect_seconds=2.2,
        uid_loop_seconds=99.9,
        total_seconds=103.2,
    )
    gmail_imap.log_gmail_ingest_phases("INBOX", timings)
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "[gmail-imap] INBOX phase auth_seconds=1.10"
    assert out[-1] == "[gmail-imap] INBOX phase total_seconds=103.20"
    assert len(out) == len(gmail_imap.GMAIL_INGEST_PHASE_FIELDS)


def test_merge_gmail_ingest_phase_timings_sums_disjoint_phases() -> None:
    script = gmail_imap.GmailIngestPhaseTimings(auth_seconds=1.0, select_seconds=0.5)
    folder = gmail_imap.GmailIngestPhaseTimings(
        existing_mids_seconds=3.0,
        uid_loop_seconds=10.0,
        commit_seconds=0.1,
    )
    merged = gmail_imap.merge_gmail_ingest_phase_timings(script, folder)
    assert merged.auth_seconds == 1.0
    assert merged.select_seconds == 0.5
    assert merged.existing_mids_seconds == 3.0
    assert merged.uid_loop_seconds == 10.0
    assert merged.commit_seconds == 0.1


def test_parse_message_id_from_header_bytes() -> None:
    raw = b"Message-ID: <preflight@origenlab.test>\r\n"
    assert gmail_imap.parse_message_id_from_header_bytes(raw) == "<preflight@origenlab.test>"
    assert gmail_imap.parse_message_id_from_header_bytes(b"") is None
    assert gmail_imap.parse_message_id_from_header_bytes(None) is None


def _sample_rfc822(*, message_id: str = "<new@origenlab.test>") -> bytes:
    return (
        b"From: Writer <writer@client.test>\r\n"
        b"To: contacto@origenlab.cl\r\n"
        b"Subject: Unit ingest\r\n"
        b"Message-ID: "
        + message_id.encode()
        + b"\r\n"
        b"\r\n"
        b"Body text.\r\n"
    )


def _header_fetch_responses(uid_arg: bytes | str, header: bytes | None) -> list[tuple[bytes, bytes]]:
    if isinstance(uid_arg, str):
        uid_arg = uid_arg.encode()
    responses: list[tuple[bytes, bytes]] = []
    for uid in uid_arg.split(b","):
        uid = uid.strip()
        if not uid:
            continue
        uid_s = uid.decode()
        meta = f"{uid_s} (UID {uid_s}) BODY[HEADER.FIELDS (MESSAGE-ID)]".encode()
        responses.append((meta, header or b""))
    return responses


class _TrackingFakeMail:
    """Records IMAP FETCH specs; no live Gmail."""

    def __init__(
        self,
        *,
        search_uid: bytes,
        header: bytes | None,
        body: bytes | None,
    ) -> None:
        self.search_uid = search_uid
        self.header = header
        self.body = body
        self.fetch_specs: list[str] = []
        self.header_fetch_uid_sets: list[bytes] = []

    def uid(self, cmd: str, *args: object) -> tuple[str, list[object] | None]:
        if cmd == "SEARCH":
            return "OK", [self.search_uid]
        if cmd == "FETCH":
            spec = str(args[-1]) if args else ""
            uid_arg = args[0] if args else b""
            self.fetch_specs.append(spec)
            if "HEADER.FIELDS" in spec:
                if isinstance(uid_arg, str):
                    uid_arg = uid_arg.encode()
                self.header_fetch_uid_sets.append(uid_arg)
                return "OK", _header_fetch_responses(uid_arg, self.header)
            if "BODY.PEEK[]" in spec:
                return "OK", [(b"meta", self.body)]
            return "NO", None
        return "NO", None

    def select(self, *args: object, **kwargs: object) -> tuple[str, None]:
        return "OK", None

    def _quote(self, s: str) -> str:
        return f'"{s}"'


class _BatchFakeMail:
    """Per-UID headers/bodies for batch preflight tests; no live Gmail."""

    def __init__(
        self,
        *,
        headers: dict[bytes, bytes | None],
        bodies: dict[bytes, bytes | None],
    ) -> None:
        self.headers = headers
        self.bodies = bodies
        self.header_fetch_uid_sets: list[bytes] = []

    def uid(self, cmd: str, *args: object) -> tuple[str, list[object] | None]:
        if cmd == "FETCH":
            spec = str(args[-1]) if args else ""
            uid_arg = args[0] if args else b""
            if isinstance(uid_arg, str):
                uid_arg = uid_arg.encode()
            if "HEADER.FIELDS" in spec:
                self.header_fetch_uid_sets.append(uid_arg)
                responses: list[tuple[bytes, bytes]] = []
                for uid in uid_arg.split(b","):
                    uid = uid.strip()
                    if not uid:
                        continue
                    uid_s = uid.decode()
                    meta = f"{uid_s} (UID {uid_s}) BODY[HEADER.FIELDS (MESSAGE-ID)]".encode()
                    responses.append((meta, self.headers.get(uid) or b""))
                return "OK", responses
            if "BODY.PEEK[]" in spec:
                uid = uid_arg.split(b",")[0].strip()
                return "OK", [(b"meta", self.bodies.get(uid))]
            return "NO", None
        return "NO", None

    def select(self, *args: object, **kwargs: object) -> tuple[str, None]:
        return "OK", None


def _ingest_conn(tmp_path: Path, *, message_id: str = "<dup@t>") -> sqlite3.Connection:
    from origenlab_email_pipeline.db import connect, init_schema, insert_email

    conn = connect(tmp_path / "ingest.sqlite")
    init_schema(conn)
    insert_email(
        conn,
        source_file="gmail:u/f",
        folder="INBOX",
        message_id=message_id,
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
    return conn


def test_fetch_message_id_headers_for_uids_batches_and_parses() -> None:
    mail = MagicMock()
    uids = [str(i).encode() for i in range(1, 251)]

    def fake_uid(cmd: str, uid_set: bytes, spec: str) -> tuple[str, list[tuple[bytes, bytes]]]:
        assert cmd == "FETCH"
        assert "HEADER.FIELDS" in spec
        responses: list[tuple[bytes, bytes]] = []
        for uid in uid_set.split(b","):
            uid = uid.strip()
            meta = f"X (UID {uid.decode()}) BODY".encode()
            responses.append((meta, b"Message-ID: <mid@t>\r\n"))
        return "OK", responses

    mail.uid.side_effect = fake_uid
    result = gmail_imap.fetch_message_id_headers_for_uids(mail, uids, chunk_size=100)
    assert len(result) == 250
    assert all(result[uid] == "<mid@t>" for uid in uids)
    assert mail.uid.call_count == 3


def test_batch_preflight_uses_fewer_header_fetches_than_uid_count(tmp_path: Path) -> None:
    conn = _ingest_conn(tmp_path)
    uid_list = [str(i).encode() for i in range(1, 6)]
    mail = _BatchFakeMail(
        headers={uid: b"Message-ID: <dup@t>\r\n" for uid in uid_list},
        bodies={},
    )
    result = gmail_imap.ingest_gmail_folder(
        conn,
        mail,
        user="u",
        folder="f",
        since_days=None,
        max_messages=0,
        replace_source=False,
        skip_duplicate_message_id=True,
        uid_iter=uid_list,
        folder_already_selected=True,
    )
    conn.close()
    assert result.skipped_dup == 5
    assert result.inserted == 0
    assert len(mail.header_fetch_uid_sets) == 1
    assert mail.header_fetch_uid_sets[0] == b"1,2,3,4,5"
    assert mail.bodies == {}


def test_batch_preflight_mixed_dup_new_and_missing_header(tmp_path: Path) -> None:
    conn = _ingest_conn(tmp_path)
    mail = _BatchFakeMail(
        headers={
            b"1": b"Message-ID: <dup@t>\r\n",
            b"2": b"Message-ID: <brand-new@origenlab.test>\r\n",
            b"3": b"Subject: no mid\r\n",
        },
        bodies={
            b"2": _sample_rfc822(message_id="<brand-new@origenlab.test>"),
            b"3": _sample_rfc822(message_id="<fallback@origenlab.test>"),
        },
    )
    result = gmail_imap.ingest_gmail_folder(
        conn,
        mail,
        user="u",
        folder="f",
        since_days=None,
        max_messages=0,
        replace_source=False,
        skip_duplicate_message_id=True,
        uid_iter=[b"1", b"2", b"3"],
        folder_already_selected=True,
    )
    n = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    assert result.skipped_dup == 1
    assert result.inserted == 2
    assert n == 3
    assert len(mail.header_fetch_uid_sets) == 1


def test_duplicate_message_id_preflight_skips_full_fetch(tmp_path: Path) -> None:
    conn = _ingest_conn(tmp_path)
    mail = _TrackingFakeMail(
        search_uid=b"9",
        header=b"Message-ID: <dup@t>\r\n",
        body=_sample_rfc822(message_id="<dup@t>"),
    )
    result = gmail_imap.ingest_gmail_folder(
        conn,
        mail,
        user="u",
        folder="f",
        since_days=None,
        max_messages=0,
        replace_source=False,
        skip_duplicate_message_id=True,
        uid_iter=[b"9"],
        folder_already_selected=True,
    )
    conn.close()
    assert result.skipped_dup == 1
    assert result.inserted == 0
    assert result.phase_timings.existing_mids_seconds >= 0
    assert result.phase_timings.uid_loop_seconds >= 0
    assert result.phase_timings.commit_seconds >= 0
    assert len(mail.fetch_specs) == 1
    assert "HEADER.FIELDS" in mail.fetch_specs[0]
    assert "BODY.PEEK[]" not in mail.fetch_specs[0]


def test_new_message_id_preflights_then_fetches_full_body(tmp_path: Path) -> None:
    conn = _ingest_conn(tmp_path)
    mail = _TrackingFakeMail(
        search_uid=b"10",
        header=b"Message-ID: <brand-new@origenlab.test>\r\n",
        body=_sample_rfc822(message_id="<brand-new@origenlab.test>"),
    )
    result = gmail_imap.ingest_gmail_folder(
        conn,
        mail,
        user="u",
        folder="f",
        since_days=None,
        max_messages=0,
        replace_source=False,
        skip_duplicate_message_id=True,
        uid_iter=[b"10"],
        folder_already_selected=True,
    )
    n = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    assert result.inserted == 1
    assert result.skipped_dup == 0
    assert len(mail.fetch_specs) == 2
    assert "HEADER.FIELDS" in mail.fetch_specs[0]
    assert "BODY.PEEK[]" in mail.fetch_specs[1]
    assert n == 2


def test_missing_header_message_id_falls_back_to_full_fetch(tmp_path: Path) -> None:
    conn = _ingest_conn(tmp_path)
    mail = _TrackingFakeMail(
        search_uid=b"11",
        header=b"Subject: no mid here\r\n",
        body=_sample_rfc822(message_id="<fallback@origenlab.test>"),
    )
    result = gmail_imap.ingest_gmail_folder(
        conn,
        mail,
        user="u",
        folder="f",
        since_days=None,
        max_messages=0,
        replace_source=False,
        skip_duplicate_message_id=True,
        uid_iter=[b"11"],
        folder_already_selected=True,
    )
    conn.close()
    assert result.inserted == 1
    assert "BODY.PEEK[]" in mail.fetch_specs[-1]


def test_skip_duplicate_disabled_uses_full_fetch_only(tmp_path: Path) -> None:
    conn = _ingest_conn(tmp_path)
    mail = _TrackingFakeMail(
        search_uid=b"12",
        header=b"Message-ID: <dup@t>\r\n",
        body=_sample_rfc822(message_id="<dup@t>"),
    )
    result = gmail_imap.ingest_gmail_folder(
        conn,
        mail,
        user="u",
        folder="f",
        since_days=None,
        max_messages=0,
        replace_source=False,
        skip_duplicate_message_id=False,
        uid_iter=[b"12"],
        folder_already_selected=True,
    )
    conn.close()
    assert result.inserted == 1
    assert result.skipped_dup == 0
    assert len(mail.fetch_specs) == 1
    assert "BODY.PEEK[]" in mail.fetch_specs[0]
    assert "HEADER.FIELDS" not in mail.fetch_specs[0]


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
    tmp_path: Path, oauth_env: dict[str, str], capsys
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

    header = b"Message-ID: <phase2-ingest@origenlab.test>\r\n"

    class FakeMail:
        def uid(self, cmd, *args):
            if cmd == "SEARCH":
                return "OK", [uid]
            if cmd == "FETCH":
                spec = str(args[-1]) if args else ""
                uid_arg = args[0] if args else uid
                if "HEADER.FIELDS" in spec:
                    return "OK", _header_fetch_responses(uid_arg, header)
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
        patch.object(sys, "argv", ["05_workspace_gmail_imap_to_sqlite.py", "--folder", "INBOX"]),
    ):
        rc1 = m.main()
    assert rc1 == 0
    first_out = capsys.readouterr().out
    assert "[gmail-imap] INBOX phase auth_seconds=" in first_out
    assert "[gmail-imap] INBOX phase uid_loop_seconds=" in first_out
    assert "[gmail-imap] INBOX phase total_seconds=" in first_out

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
    second_out = capsys.readouterr().out
    assert "[gmail-imap] INBOX phase existing_mids_seconds=" in second_out
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
