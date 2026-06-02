"""Ingest helpers (Gmail Workspace IMAP → SQLite)."""

from origenlab_email_pipeline.ingest.gmail_imap import (
    IngestFolderResult,
    delete_emails_for_source_file,
    fetch_rfc822,
    format_error_counts,
    imap_select_folder,
    ingest_gmail_folder,
    ingest_parsed_message_to_sqlite,
    list_mailbox_names,
    load_existing_message_ids,
    mailbox_name_from_list_line,
    message_from_bytes,
    search_uids,
    source_label,
)

__all__ = [
    "IngestFolderResult",
    "delete_emails_for_source_file",
    "fetch_rfc822",
    "format_error_counts",
    "imap_select_folder",
    "ingest_gmail_folder",
    "ingest_parsed_message_to_sqlite",
    "list_mailbox_names",
    "load_existing_message_ids",
    "mailbox_name_from_list_line",
    "message_from_bytes",
    "search_uids",
    "source_label",
]
