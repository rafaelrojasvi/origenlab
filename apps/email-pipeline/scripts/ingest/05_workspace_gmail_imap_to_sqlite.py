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
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect, init_schema
from origenlab_email_pipeline.ingest.gmail_imap import (
    GmailIngestPhaseTimings,
    format_error_counts,
    imap_select_folder,
    ingest_gmail_folder,
    list_mailbox_names,
    log_gmail_ingest_phases,
    merge_gmail_ingest_phase_timings,
    search_uids,
)

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # type: ignore[misc, assignment]


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
    # Break-glass: deletes existing rows for this mailbox source_file before reinsert.
    ap.add_argument("--replace-source", action="store_true")
    ap.add_argument("--skip-duplicate-message-id", action="store_true")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--list-folders",
        action="store_true",
        help="Print all IMAP mailbox names (use exact string for --folder) and exit",
    )
    args = ap.parse_args()

    total_start = time.perf_counter()
    phase_timings = GmailIngestPhaseTimings()

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

    auth_start = time.perf_counter()
    creds = load_credentials_for_gmail_imap(
        client_secrets_json=client_path,
        token_json=token_path,
        open_browser=settings.gmail_oauth_open_browser,
    )
    phase_timings.auth_seconds = round(time.perf_counter() - auth_start, 2)
    token = creds.token
    if not token:
        print("No access token after OAuth; try deleting token file and re-authorizing.", file=sys.stderr)
        return 1

    db_path = args.db or settings.resolved_sqlite_path()

    connect_start = time.perf_counter()
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        xoauth2_authenticate(mail, user, token)
    except imaplib.IMAP4.error as e:
        phase_timings.connect_seconds = round(time.perf_counter() - connect_start, 2)
        print(f"IMAP XOAUTH2 failed: {e}", file=sys.stderr)
        try:
            mail.logout()
        except Exception:
            pass
        return 1
    phase_timings.connect_seconds = round(time.perf_counter() - connect_start, 2)

    if args.list_folders:
        try:
            for mb in list_mailbox_names(mail):
                print(mb)
        except imaplib.IMAP4.error:
            print("IMAP LIST failed.", file=sys.stderr)
            return 1
        finally:
            try:
                mail.logout()
            except Exception:
                pass
        return 0

    inserted = 0
    skipped_dup = 0
    skipped_fetch = 0
    message_errors = 0
    attachment_errors = 0
    message_error_types = None
    attachment_error_types = None
    uids: list[bytes] = []

    db_open_start = time.perf_counter()
    conn = connect(db_path)
    try:
        init_schema(conn)
        phase_timings.db_open_seconds = round(time.perf_counter() - db_open_start, 2)

        try:
            select_start = time.perf_counter()
            typ, _ = imap_select_folder(mail, args.folder, readonly=True)
            if typ != "OK":
                raise imaplib.IMAP4.error(f"select failed: {args.folder!r}")
            phase_timings.select_seconds = round(time.perf_counter() - select_start, 2)

            search_start = time.perf_counter()
            uids = search_uids(mail, since_days=args.since_days)
            phase_timings.search_seconds = round(time.perf_counter() - search_start, 2)
            if args.max_messages and args.max_messages > 0 and len(uids) > args.max_messages:
                uids = uids[-args.max_messages :]

            uid_iter = uids
            if tqdm is not None:
                uid_iter = tqdm(uids, desc=f"Gmail {args.folder}", unit="msg")

            result = ingest_gmail_folder(
                conn,
                mail,
                user=user,
                folder=args.folder,
                since_days=args.since_days,
                max_messages=args.max_messages,
                replace_source=args.replace_source,
                skip_duplicate_message_id=args.skip_duplicate_message_id,
                uid_iter=uid_iter,
                folder_already_selected=True,
            )
            phase_timings = merge_gmail_ingest_phase_timings(phase_timings, result.phase_timings)
            inserted = result.inserted
            skipped_dup = result.skipped_dup
            skipped_fetch = result.skipped_fetch
            message_errors = result.message_errors
            attachment_errors = result.attachment_errors
            message_error_types = result.message_error_types
            attachment_error_types = result.attachment_error_types
            uids = result.uids
        except imaplib.IMAP4.error:
            print(
                f"Could not select folder {args.folder!r}. "
                "Gmail label names depend on account language. "
                "Run the same command with --list-folders and use the exact line for --folder.",
                file=sys.stderr,
            )
            return 1
        finally:
            close_start = time.perf_counter()
            try:
                mail.logout()
            except Exception:
                pass
            phase_timings.close_logout_seconds = round(time.perf_counter() - close_start, 2)
    finally:
        conn.close()

    phase_timings.total_seconds = round(time.perf_counter() - total_start, 2)
    log_gmail_ingest_phases(args.folder, phase_timings)
    print(f"SQLite: {db_path}  inserted={inserted}")
    print(
        f"Gmail IMAP summary: uids={len(uids)} inserted={inserted} skipped_dup_mid={skipped_dup} "
        f"skipped_fetch={skipped_fetch} message_errors={message_errors} attachment_errors={attachment_errors}"
    )
    if message_errors and message_error_types is not None:
        print("Top message error types:", format_error_counts(message_error_types))
    if attachment_errors and attachment_error_types is not None:
        print("Top attachment error types:", format_error_counts(attachment_error_types))
    return 0 if message_errors == 0 or inserted > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
