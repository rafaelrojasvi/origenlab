"""Gmail Workspace IMAP ingest helpers (used by scripts/ingest/05_workspace_gmail_imap_to_sqlite.py)."""

from __future__ import annotations

import imaplib
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from typing import Literal

from origenlab_email_pipeline.db import insert_attachment, insert_email
from origenlab_email_pipeline.parse_mbox import (
    body_content,
    date_iso_from_msg,
    extract_body_structured,
    extract_full_and_top_reply,
    recipients_header,
    walk_attachments,
)

# imaplib passes mailbox names to the wire unquoted; `[Gmail]/Sent Mail` then parses as BAD.
_IMAP_SIMPLE_MAILBOX = re.compile(r"[A-Za-z0-9._+-]+")

IngestMessageOutcome = Literal["inserted", "skipped_dup", "skipped_fetch"]


@dataclass
class IngestFolderResult:
    """Counters from one folder ingest pass (matches CLI summary fields)."""

    uids: list[bytes]
    inserted: int = 0
    skipped_dup: int = 0
    skipped_fetch: int = 0
    message_errors: int = 0
    attachment_errors: int = 0
    message_error_types: Counter[str] = field(default_factory=Counter)
    attachment_error_types: Counter[str] = field(default_factory=Counter)


def source_label(user: str, folder: str) -> str:
    return f"gmail:{user}/{folder}"


def imap_select_folder(mail: imaplib.IMAP4_SSL, folder: str, *, readonly: bool):
    mbox = folder if _IMAP_SIMPLE_MAILBOX.fullmatch(folder) else mail._quote(folder)
    return mail.select(mbox, readonly=readonly)


def mailbox_name_from_list_line(line: bytes) -> str:
    """Decode mailbox name from one IMAP LIST untagged payload (Gmail: flags + delimiter + name)."""
    if not line or not line.strip():
        return ""
    s = line.decode("utf-8", "replace").strip()
    sep = ') "/" '
    idx = s.find(sep)
    rest = s[idx + len(sep) :].strip() if idx >= 0 else s
    if idx < 0:
        m = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', s)
        if m:
            inner = m.group(1).replace("\\\\", "\\").replace('\\"', '"')
            return inner
        return ""
    if rest.startswith('"'):
        out: list[str] = []
        i = 1
        while i < len(rest):
            c = rest[i]
            if c == "\\":
                i += 1
                if i < len(rest):
                    out.append(rest[i])
                i += 1
            elif c == '"':
                return "".join(out)
            else:
                out.append(c)
                i += 1
        return "".join(out)
    return rest.split()[0] if rest else ""


def list_mailbox_names(mail: imaplib.IMAP4_SSL) -> list[str]:
    typ, dat = mail.list()
    if typ != "OK":
        raise imaplib.IMAP4.error("IMAP LIST failed")
    names: list[str] = []
    for item in dat or []:
        if not item:
            continue
        raw = item if isinstance(item, (bytes, bytearray)) else str(item).encode()
        mb = mailbox_name_from_list_line(bytes(raw))
        if mb:
            names.append(mb)
    names.sort()
    return names


def search_uids(mail: imaplib.IMAP4_SSL, *, since_days: int | None) -> list[bytes]:
    if since_days is not None and since_days > 0:
        dt = datetime.now(timezone.utc) - timedelta(days=since_days)
        since = dt.strftime("%d-%b-%Y")
        typ, data = mail.uid("SEARCH", None, "SINCE", since)
    else:
        typ, data = mail.uid("SEARCH", None, "ALL")
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def fetch_rfc822(mail: imaplib.IMAP4_SSL, uid: bytes) -> bytes | None:
    typ, data = mail.uid("FETCH", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data:
        return None
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            return item[1] if isinstance(item[1], (bytes, bytearray)) else None
    return None


def fetch_message_id_header(mail: imaplib.IMAP4_SSL, uid: bytes) -> bytes | None:
    """Lightweight Message-ID preflight (no RFC822 body download)."""
    typ, data = mail.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    if typ != "OK" or not data:
        return None
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            payload = item[1]
            if isinstance(payload, (bytes, bytearray)):
                return bytes(payload)
    return None


def parse_message_id_from_header_bytes(raw: bytes | None) -> str | None:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.lower().startswith("message-id:"):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


def normalize_message_id(message_id: str | None) -> str:
    return (message_id or "").strip().lower()


def message_from_bytes(raw: bytes) -> Message:
    return BytesParser(policy=policy.default).parsebytes(raw)


def format_error_counts(counter: Counter[str], *, top_n: int = 5) -> str:
    if not counter:
        return "(none)"
    return ", ".join(f"{name}={count}" for name, count in counter.most_common(top_n))


def load_existing_message_ids(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT message_id FROM emails WHERE message_id IS NOT NULL AND trim(message_id) != ''"
    )
    return {str(r[0]).strip().lower() for r in cur.fetchall() if r[0]}


def delete_emails_for_source_file(conn: sqlite3.Connection, source_file: str) -> None:
    """Break-glass: remove all rows for one gmail: user/folder source_file before reinsert."""
    conn.execute("DELETE FROM emails WHERE source_file = ?", (source_file,))
    conn.commit()


def ingest_parsed_message_to_sqlite(
    conn: sqlite3.Connection,
    msg: Message,
    *,
    source_file: str,
    folder: str,
    existing_mids: set[str],
    skip_duplicate_message_id: bool,
) -> tuple[IngestMessageOutcome, Counter[str]]:
    """Insert one parsed message. Returns (outcome, attachment error types for this message)."""
    mid = msg.get("Message-ID")
    mid_norm = (mid or "").strip().lower()
    if skip_duplicate_message_id and mid_norm and mid_norm in existing_mids:
        return "skipped_dup", Counter()

    body, body_html = body_content(msg)
    structured = extract_body_structured(msg)
    full_body_clean, top_reply_clean = extract_full_and_top_reply(structured)
    attachments = walk_attachments(msg)
    email_id = insert_email(
        conn,
        source_file=source_file,
        folder=folder,
        message_id=mid,
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
        attachment_count=len(attachments),
        has_attachments=bool(attachments),
    )
    if mid_norm:
        existing_mids.add(mid_norm)
    attachment_error_types: Counter[str] = Counter()
    for att in attachments:
        try:
            insert_attachment(
                conn,
                email_id=email_id,
                part_index=att["part_index"],
                filename=att["filename"],
                content_type=att["content_type"],
                content_disposition=att["content_disposition"],
                size_bytes=att["size_bytes"],
                content_id=att["content_id"],
                is_inline=att["is_inline"],
                sha256=att["sha256"],
                saved_path=att["saved_path"],
                created_at=None,
            )
        except Exception as exc:
            attachment_error_types[type(exc).__name__] += 1
    return "inserted", attachment_error_types


def ingest_gmail_folder(
    conn: sqlite3.Connection,
    mail: imaplib.IMAP4_SSL,
    *,
    user: str,
    folder: str,
    since_days: int | None,
    max_messages: int,
    replace_source: bool,
    skip_duplicate_message_id: bool,
    uid_iter: Iterable[bytes] | None = None,
    folder_already_selected: bool = False,
) -> IngestFolderResult:
    """Ingest messages from one folder. Commits once at end.

    When ``uid_iter`` is provided (e.g. tqdm-wrapped), the caller must already have
    selected the folder and trimmed UID lists; ``since_days`` / ``max_messages`` are ignored.
    """
    source_file = source_label(user, folder)
    existing_mids: set[str] = set()
    if skip_duplicate_message_id:
        existing_mids = load_existing_message_ids(conn)
    if replace_source:
        delete_emails_for_source_file(conn, source_file)

    if uid_iter is None:
        typ, _ = imap_select_folder(mail, folder, readonly=True)
        if typ != "OK":
            raise imaplib.IMAP4.error(f"Could not select folder {folder!r}")
        uids = search_uids(mail, since_days=since_days)
        if max_messages and max_messages > 0 and len(uids) > max_messages:
            uids = uids[-max_messages:]
    else:
        if not folder_already_selected:
            typ, _ = imap_select_folder(mail, folder, readonly=True)
            if typ != "OK":
                raise imaplib.IMAP4.error(f"Could not select folder {folder!r}")
        uids = list(uid_iter)

    result = IngestFolderResult(uids=uids)
    for uid in uids:
        try:
            if skip_duplicate_message_id:
                header_raw = fetch_message_id_header(mail, uid)
                mid_from_header = parse_message_id_from_header_bytes(header_raw)
                mid_norm = normalize_message_id(mid_from_header)
                if mid_norm and mid_norm in existing_mids:
                    result.skipped_dup += 1
                    continue

            raw = fetch_rfc822(mail, uid)
            if not raw:
                result.skipped_fetch += 1
                continue
            msg = message_from_bytes(raw)
            outcome, att_err_types = ingest_parsed_message_to_sqlite(
                conn,
                msg,
                source_file=source_file,
                folder=folder,
                existing_mids=existing_mids,
                skip_duplicate_message_id=skip_duplicate_message_id,
            )
            if outcome == "skipped_dup":
                result.skipped_dup += 1
                continue
            if att_err_types:
                result.attachment_errors += sum(att_err_types.values())
                result.attachment_error_types.update(att_err_types)
            result.inserted += 1
        except Exception as exc:
            result.message_errors += 1
            result.message_error_types[type(exc).__name__] += 1
            continue

    conn.commit()
    return result
