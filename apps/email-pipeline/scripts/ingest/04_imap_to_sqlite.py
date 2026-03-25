#!/usr/bin/env python3
"""
Fetch mail over **IMAP** (SSL) and insert into the same `emails` SQLite schema as mbox ingest.

Designed for **contacto@origenlab.cl** on **Titan** (`imap.titan.email`), not Gmail API.
See docs/ingest/IMAP_CONTACTO.md and docs/ingest/GMAIL_API.md.

Env (recommended in `.env`, never commit secrets):
  ORIGENLAB_IMAP_HOST   default: imap.titan.email
  ORIGENLAB_IMAP_PORT   default: 993
  ORIGENLAB_IMAP_USER   e.g. contacto@origenlab.cl
  ORIGENLAB_IMAP_PASSWORD

Does **not** delete existing rows unless you pass --replace-source (then only rows with
matching source_file prefix are removed before insert).
"""

from __future__ import annotations

import argparse
import imaplib
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect, init_schema, insert_attachment, insert_email
from origenlab_email_pipeline.parse_mbox import (
    body_content,
    date_iso_from_msg,
    extract_body_structured,
    extract_full_and_top_reply,
    recipients_header,
    walk_attachments,
)

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # type: ignore[misc, assignment]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, "").strip()
    return v if v else default


def _source_label(user: str, folder: str) -> str:
    return f"imap:{user}/{folder}"


def _search_uids(mail: imaplib.IMAP4_SSL, *, since_days: int | None) -> list[bytes]:
    if since_days is not None and since_days > 0:
        dt = datetime.now(timezone.utc) - timedelta(days=since_days)
        since = dt.strftime("%d-%b-%Y")
        typ, data = mail.uid("SEARCH", None, "SINCE", since)
    else:
        typ, data = mail.uid("SEARCH", None, "ALL")
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _fetch_rfc822(mail: imaplib.IMAP4_SSL, uid: bytes) -> bytes | None:
    # BODY.PEEK avoids setting \\Seen on servers that respect it.
    typ, data = mail.uid("FETCH", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data:
        return None
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            return item[1] if isinstance(item[1], (bytes, bytearray)) else None
    return None


def _message_from_bytes(raw: bytes) -> Message:
    return BytesParser(policy=policy.default).parsebytes(raw)


def _fmt_error_counts(counter: Counter[str], *, top_n: int = 5) -> str:
    if not counter:
        return "(none)"
    return ", ".join(f"{name}={count}" for name, count in counter.most_common(top_n))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", default="INBOX", help="IMAP folder (default INBOX)")
    ap.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only messages on or after this many days ago (UTC-based SINCE); omit for all",
    )
    ap.add_argument(
        "--max-messages",
        type=int,
        default=0,
        help="Cap messages fetched after search (keeps newest UIDs when sorted; 0 = no cap)",
    )
    ap.add_argument(
        "--replace-source",
        action="store_true",
        help="Delete existing rows whose source_file equals this run's imap:... label, then insert",
    )
    ap.add_argument(
        "--skip-duplicate-message-id",
        action="store_true",
        help="Skip insert if a row with the same non-empty Message-ID already exists",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default from settings)")
    args = ap.parse_args()

    host = _env("ORIGENLAB_IMAP_HOST", "imap.titan.email")
    port_s = _env("ORIGENLAB_IMAP_PORT", "993")
    user = _env("ORIGENLAB_IMAP_USER")
    password = _env("ORIGENLAB_IMAP_PASSWORD")
    if not host or not user or not password:
        print(
            "Set ORIGENLAB_IMAP_USER and ORIGENLAB_IMAP_PASSWORD (and optionally "
            "ORIGENLAB_IMAP_HOST / ORIGENLAB_IMAP_PORT) in the environment or .env.",
            file=sys.stderr,
        )
        return 2
    try:
        port = int(port_s or "993")
    except ValueError:
        print("Invalid ORIGENLAB_IMAP_PORT", file=sys.stderr)
        return 2

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    source_file = _source_label(user, args.folder)

    conn = connect(db_path)
    init_schema(conn)

    existing_mids: set[str] = set()
    if args.skip_duplicate_message_id:
        cur = conn.execute(
            "SELECT message_id FROM emails WHERE message_id IS NOT NULL AND trim(message_id) != ''"
        )
        existing_mids = {str(r[0]).strip().lower() for r in cur.fetchall() if r[0]}

    if args.replace_source:
        conn.execute("DELETE FROM emails WHERE source_file = ?", (source_file,))
        conn.commit()

    mail = imaplib.IMAP4_SSL(host, port)
    try:
        mail.login(user, password)
    except imaplib.IMAP4.error as e:
        print(f"IMAP login failed: {e}", file=sys.stderr)
        return 1

    try:
        typ, _ = mail.select(args.folder, readonly=True)
        if typ != "OK":
            print(f"Could not select folder {args.folder!r}", file=sys.stderr)
            return 1

        uids = _search_uids(mail, since_days=args.since_days)
        if args.max_messages and args.max_messages > 0 and len(uids) > args.max_messages:
            uids = uids[-args.max_messages :]

        iterator = uids
        if tqdm is not None:
            iterator = tqdm(uids, desc=f"IMAP {args.folder}", unit="msg")

        inserted = 0
        skipped_dup = 0
        skipped_fetch = 0
        message_errors = 0
        attachment_errors = 0
        message_error_types: Counter[str] = Counter()
        attachment_error_types: Counter[str] = Counter()
        per_uid_errors: dict[str, int] = defaultdict(int)

        for uid in iterator:
            try:
                raw = _fetch_rfc822(mail, uid)
                if not raw:
                    skipped_fetch += 1
                    continue
                msg = _message_from_bytes(raw)
                mid = msg.get("Message-ID")
                mid_norm = (mid or "").strip().lower()
                if args.skip_duplicate_message_id and mid_norm and mid_norm in existing_mids:
                    skipped_dup += 1
                    continue

                body, body_html = body_content(msg)
                structured = extract_body_structured(msg)
                full_body_clean, top_reply_clean = extract_full_and_top_reply(structured)
                attachments = walk_attachments(msg)
                email_id = insert_email(
                    conn,
                    source_file=source_file,
                    folder=args.folder,
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
                        attachment_errors += 1
                        attachment_error_types[type(exc).__name__] += 1
                inserted += 1
            except Exception as exc:
                message_errors += 1
                message_error_types[type(exc).__name__] += 1
                per_uid_errors[uid.decode(errors="replace")] += 1
                continue

        conn.commit()
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    conn.close()

    print(f"SQLite: {db_path}  inserted={inserted}")
    print(
        f"IMAP summary: uids={len(uids)} inserted={inserted} skipped_dup_mid={skipped_dup} "
        f"skipped_fetch={skipped_fetch} message_errors={message_errors} attachment_errors={attachment_errors}"
    )
    if message_errors:
        print("Top message error types:", _fmt_error_counts(message_error_types))
    if attachment_errors:
        print("Top attachment error types:", _fmt_error_counts(attachment_error_types))
    return 0 if message_errors == 0 or inserted > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
