"""LIST response parsing for Gmail IMAP folder names."""

from __future__ import annotations

from origenlab_email_pipeline.ingest import gmail_imap


def test_mailbox_name_from_list_line_quoted() -> None:
    raw = br'(\HasNoChildren) "/" "[Gmail]/Sent Mail"'
    assert gmail_imap.mailbox_name_from_list_line(raw) == "[Gmail]/Sent Mail"


def test_mailbox_name_from_list_line_inbox_atom() -> None:
    raw = br'(\HasNoChildren) "/" INBOX'
    assert gmail_imap.mailbox_name_from_list_line(raw) == "INBOX"
