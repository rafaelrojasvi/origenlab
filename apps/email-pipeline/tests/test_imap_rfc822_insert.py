"""RFC822 bytes → parse_mbox → insert_email (same path as 04_imap_to_sqlite)."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from origenlab_email_pipeline.db import connect, init_schema, insert_email
from origenlab_email_pipeline.parse_mbox import (
    body_content,
    date_iso_from_msg,
    extract_body_structured,
    extract_full_and_top_reply,
    recipients_header,
)


def test_minimal_rfc822_inserts(tmp_path: Path) -> None:
    raw = (
        b"From: Writer <writer@labdelivery.cl>\r\n"
        b"To: Client <client@example.com>\r\n"
        b"Subject: Cotizaci\xf3n\r\n"
        b"Message-ID: <unit-test-imap-msg@origenlab.test>\r\n"
        b"\r\n"
        b"Estimado cliente, adjunto informaci\xf3n.\r\n"
    )
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    db = tmp_path / "t.sqlite"
    conn = connect(db)
    init_schema(conn)
    structured = extract_body_structured(msg)
    full_body_clean, top_reply_clean = extract_full_and_top_reply(structured)
    body, body_html = body_content(msg)
    eid = insert_email(
        conn,
        source_file="imap:test/INBOX",
        folder="INBOX",
        message_id=msg.get("Message-ID"),
        subject=msg.get("Subject"),
        sender=msg.get("From"),
        recipients=recipients_header(msg),
        date_raw=msg.get("Date"),
        date_iso=date_iso_from_msg(msg),
        body=body,
        body_html=body_html,
        body_text_raw=structured["body_text_raw"],
        body_text_clean=structured["body_text_clean"],
        body_source_type=structured["body_source_type"],
        body_has_plain=structured["body_has_plain"],
        body_has_html=structured["body_has_html"],
        full_body_clean=full_body_clean,
        top_reply_clean=top_reply_clean,
        attachment_count=0,
        has_attachments=False,
    )
    conn.commit()
    assert eid >= 1
    row = conn.execute("SELECT sender, subject, source_file FROM emails WHERE id = ?", (eid,)).fetchone()
    assert row is not None
    assert "writer@labdelivery.cl" in (row[0] or "")
    assert "Cotiz" in (row[1] or "")
    assert row[2] == "imap:test/INBOX"
    conn.close()
