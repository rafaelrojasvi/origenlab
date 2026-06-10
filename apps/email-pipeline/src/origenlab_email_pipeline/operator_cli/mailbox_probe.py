"""Read-only Gmail mailbox snapshots for auto-refresh change detection."""

from __future__ import annotations

import imaplib
from dataclasses import dataclass
from datetime import datetime, timezone

from origenlab_email_pipeline.config import Settings, load_settings
from origenlab_email_pipeline.ingest.gmail_imap import imap_select_folder, search_uids
from origenlab_email_pipeline.operator_cli.constants import (
    GMAIL_INGEST_INBOX_FOLDER,
    GMAIL_INGEST_SENT_FOLDER,
)


@dataclass(frozen=True)
class MailboxFolderSnapshot:
    folder: str
    uid_count: int
    max_uid: int | None


@dataclass(frozen=True)
class MailboxSnapshot:
    inbox: MailboxFolderSnapshot
    sent: MailboxFolderSnapshot
    probed_at_utc: str

    @property
    def inbox_total(self) -> int:
        return self.inbox.uid_count

    @property
    def sent_total(self) -> int:
        return self.sent.uid_count


def _max_uid_from_list(uids: list[bytes]) -> int | None:
    if not uids:
        return None
    return max(int(uid) for uid in uids)


def probe_folder_snapshot(mail: imaplib.IMAP4_SSL, folder: str) -> MailboxFolderSnapshot:
    imap_select_folder(mail, folder, readonly=True)
    uids = search_uids(mail, since_days=None)
    return MailboxFolderSnapshot(folder=folder, uid_count=len(uids), max_uid=_max_uid_from_list(uids))


def connect_gmail_imap_readonly(settings: Settings | None = None) -> tuple[imaplib.IMAP4_SSL, str]:
    """Connect to Gmail IMAP with OAuth (read-only SELECT only)."""
    settings = settings or load_settings()
    try:
        from origenlab_email_pipeline.gmail_workspace_oauth import (
            load_credentials_for_gmail_imap,
            xoauth2_authenticate,
        )
    except ImportError as exc:
        raise RuntimeError("Missing Google OAuth libraries. Run: uv sync --group gmail") from exc

    client_json = (settings.gmail_oauth_client_json or "").strip() or None
    user = (settings.gmail_workspace_user or "").strip() or None
    if not client_json or not user:
        raise RuntimeError(
            "Set ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON and ORIGENLAB_GMAIL_WORKSPACE_USER in .env."
        )

    from pathlib import Path

    default_token = settings.data_root / "secrets" / "gmail_workspace_token.json"
    token_override = (settings.gmail_token_json or "").strip()
    token_path = Path(token_override if token_override else default_token)
    client_path = Path(client_json).expanduser()
    if not client_path.is_file():
        raise RuntimeError(f"OAuth client file not found: {client_path}")

    creds = load_credentials_for_gmail_imap(
        client_secrets_json=client_path,
        token_json=token_path,
        open_browser=settings.gmail_oauth_open_browser,
    )
    token = creds.token
    if not token:
        raise RuntimeError("No access token after OAuth.")

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    xoauth2_authenticate(mail, user, token)
    return mail, user


def probe_mailbox_snapshot(
    *,
    inbox_folder: str = GMAIL_INGEST_INBOX_FOLDER,
    sent_folder: str = GMAIL_INGEST_SENT_FOLDER,
    settings: Settings | None = None,
) -> MailboxSnapshot:
    """Live IMAP UID counts for INBOX and Sent (read-only)."""
    mail, _user = connect_gmail_imap_readonly(settings)
    try:
        inbox = probe_folder_snapshot(mail, inbox_folder)
        sent = probe_folder_snapshot(mail, sent_folder)
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    probed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return MailboxSnapshot(inbox=inbox, sent=sent, probed_at_utc=probed_at)
