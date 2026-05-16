#!/usr/bin/env python3
"""
Google **Workspace** mailbox → SQLite via **Gmail IMAP** + **OAuth2** (XOAUTH2).

For Case A: **contacto@origenlab.cl** is a real Workspace user; mail lives in Gmail, not Titan.

Requires optional deps:
  uv sync --group gmail
  # (equivalent: uv sync --group workspace)

Env / files:
  ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON  path to Google Cloud "Desktop" OAuth client JSON (download)
  ORIGENLAB_GMAIL_TOKEN_JSON         path to store refresh token (create on first browser login)
  ORIGENLAB_GMAIL_WORKSPACE_USER     full address, e.g. contacto@origenlab.cl

First run opens a browser for consent; later runs refresh the token automatically.

IMAP host is always **imap.gmail.com:993**. Folder defaults to **INBOX**; Sent is often
`[Gmail]/Sent Mail` (locale-dependent — check Gmail → Settings → Labels).

See docs/ingest/WORKSPACE_GMAIL_IMAP.md
"""

from __future__ import annotations

import argparse
import imaplib
import re
import sys
from collections import Counter
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


def _source_label(user: str, folder: str) -> str:
    return f"gmail:{user}/{folder}"


# imaplib passes mailbox names to the wire unquoted; `[Gmail]/Sent Mail` then parses as BAD.
_IMAP_SIMPLE_MAILBOX = re.compile(r"[A-Za-z0-9._+-]+")


def _imap_select_folder(mail: imaplib.IMAP4_SSL, folder: str, *, readonly: bool):
    mbox = folder if _IMAP_SIMPLE_MAILBOX.fullmatch(folder) else mail._quote(folder)
    return mail.select(mbox, readonly=readonly)


def _mailbox_name_from_list_line(line: bytes) -> str:
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
    try:
        from origenlab_email_pipeline.gmail_workspace_oauth import (
            load_credentials_for_gmail_imap,
            xoauth2_authenticate,
        )
    except ImportError:
        print(
            "Missing Google OAuth libraries. Run: uv sync --group gmail",
            file=sys.stderr,
        )
        return 2

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", default="INBOX", help="Gmail IMAP folder (default INBOX)")
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--max-messages", type=int, default=0)
    ap.add_argument("--replace-source", action="store_true")
    ap.add_argument("--skip-duplicate-message-id", action="store_true")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--list-folders",
        action="store_true",
        help="Print all IMAP mailbox names (use exact string for --folder) and exit",
    )
    args = ap.parse_args()

    settings = load_settings()
    client_json = (settings.gmail_oauth_client_json or "").strip() or None
    user = (settings.gmail_workspace_user or "").strip() or None
    default_token = settings.data_root / "secrets" / "gmail_workspace_token.json"
    token_override = (settings.gmail_token_json or "").strip()
    token_path = Path(token_override if token_override else default_token)

    if not client_json or not user:
        print(
            "Set ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON and ORIGENLAB_GMAIL_WORKSPACE_USER "
            "(and optionally ORIGENLAB_GMAIL_TOKEN_JSON) in .env.",
            file=sys.stderr,
        )
        return 2

    client_path = Path(client_json).expanduser()
    if not client_path.is_file():
        print(f"OAuth client file not found: {client_path}", file=sys.stderr)
        return 2

    creds = load_credentials_for_gmail_imap(
        client_secrets_json=client_path,
        token_json=token_path,
        open_browser=settings.gmail_oauth_open_browser,
    )
    token = creds.token
    if not token:
        print("No access token after OAuth; try deleting token file and re-authorizing.", file=sys.stderr)
        return 1

    db_path = args.db or settings.resolved_sqlite_path()

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        xoauth2_authenticate(mail, user, token)
    except imaplib.IMAP4.error as e:
        print(f"IMAP XOAUTH2 failed: {e}", file=sys.stderr)
        try:
            mail.logout()
        except Exception:
            pass
        return 1

    if args.list_folders:
        typ, dat = mail.list()
        if typ != "OK":
            print("IMAP LIST failed.", file=sys.stderr)
            try:
                mail.logout()
            except Exception:
                pass
            return 1
        names: list[str] = []
        for item in dat or []:
            if not item:
                continue
            raw = item if isinstance(item, (bytes, bytearray)) else str(item).encode()
            mb = _mailbox_name_from_list_line(bytes(raw))
            if mb:
                names.append(mb)
        names.sort()
        for mb in names:
            print(mb)
        try:
            mail.logout()
        except Exception:
            pass
        return 0

    source_file = _source_label(user, args.folder)

    conn = connect(db_path)
    try:
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

        uids: list[bytes] = []
        try:
            typ, _ = _imap_select_folder(mail, args.folder, readonly=True)
            if typ != "OK":
                print(
                    f"Could not select folder {args.folder!r}. "
                    "Gmail label names depend on account language. "
                    "Run the same command with --list-folders and use the exact line for --folder.",
                    file=sys.stderr,
                )
                return 1

            uids = _search_uids(mail, since_days=args.since_days)
            if args.max_messages and args.max_messages > 0 and len(uids) > args.max_messages:
                uids = uids[-args.max_messages :]

            iterator = uids
            if tqdm is not None:
                iterator = tqdm(uids, desc=f"Gmail {args.folder}", unit="msg")

            inserted = 0
            skipped_dup = 0
            skipped_fetch = 0
            message_errors = 0
            attachment_errors = 0
            message_error_types: Counter[str] = Counter()
            attachment_error_types: Counter[str] = Counter()

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
                    continue

            conn.commit()
        finally:
            try:
                mail.logout()
            except Exception:
                pass
    finally:
        conn.close()

    print(f"SQLite: {db_path}  inserted={inserted}")
    print(
        f"Gmail IMAP summary: uids={len(uids)} inserted={inserted} skipped_dup_mid={skipped_dup} "
        f"skipped_fetch={skipped_fetch} message_errors={message_errors} attachment_errors={attachment_errors}"
    )
    if message_errors:
        print("Top message error types:", _fmt_error_counts(message_error_types))
    if attachment_errors:
        print("Top attachment error types:", _fmt_error_counts(attachment_error_types))
    return 0 if message_errors == 0 or inserted > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
