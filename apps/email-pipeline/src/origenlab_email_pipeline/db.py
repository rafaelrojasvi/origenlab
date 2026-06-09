"""Foundation SQLite layer: raw archive + mart DDL and connection helpers.

`init_schema` owns `emails` / `attachments` DDL (and related migrations), pulls in pipeline-meta
and business-mart table definitions, and is the first step in `sqlite_migrate.migrate_sqlite_schema`.
Ingest scripts insert rows; domain scoring and reporting live in other modules.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.business_mart_schema import BUSINESS_MART_SCHEMA_SQL
from origenlab_email_pipeline.core.mart.email_mart_features_schema import (
    ensure_email_mart_features_table,
)
from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    folder TEXT,
    message_id TEXT,
    subject TEXT,
    sender TEXT,
    recipients TEXT,
    date_raw TEXT,
    date_iso TEXT,
    body TEXT,
    body_html TEXT,
    body_text_raw TEXT,
    body_text_clean TEXT,
    body_source_type TEXT,
    body_has_plain INTEGER,
    body_has_html INTEGER,
    full_body_clean TEXT,
    top_reply_clean TEXT,
    attachment_count INTEGER,
    has_attachments INTEGER
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL,
    part_index INTEGER NOT NULL,
    filename TEXT,
    content_type TEXT,
    content_disposition TEXT,
    size_bytes INTEGER,
    content_id TEXT,
    is_inline INTEGER,
    sha256 TEXT,
    saved_path TEXT,
    created_at TEXT,
    FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS attachment_extracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attachment_id INTEGER NOT NULL UNIQUE,
    extract_status TEXT NOT NULL,
    extract_method TEXT NOT NULL,
    text_preview TEXT,
    text_truncated TEXT,
    char_count INTEGER,
    page_count INTEGER,
    sheet_count INTEGER,
    detected_doc_type TEXT,
    has_quote_terms INTEGER,
    has_invoice_terms INTEGER,
    has_price_list_terms INTEGER,
    has_purchase_terms INTEGER,
    error_message TEXT,
    created_at TEXT,
    FOREIGN KEY(attachment_id) REFERENCES attachments(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);
CREATE INDEX IF NOT EXISTS idx_emails_date_iso ON emails(date_iso);
CREATE INDEX IF NOT EXISTS idx_attachments_email_id ON attachments(email_id);
CREATE INDEX IF NOT EXISTS idx_attachments_sha256 ON attachments(sha256);
CREATE INDEX IF NOT EXISTS idx_attachment_extracts_attachment_id ON attachment_extracts(attachment_id);
CREATE INDEX IF NOT EXISTS idx_attachment_extracts_doc_type ON attachment_extracts(detected_doc_type);
CREATE INDEX IF NOT EXISTS idx_attachment_extracts_status_method ON attachment_extracts(extract_status, extract_method);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    ensure_pipeline_meta_tables(conn)
    conn.executescript(SCHEMA_SQL)
    conn.executescript(BUSINESS_MART_SCHEMA_SQL)
    ensure_email_mart_features_table(conn)
    # Additive migrations for business mart tables (safe on older DBs)
    for col in (
        "extracted_preview_raw TEXT",
        "extracted_preview_clean TEXT",
        "preview_quality_score REAL",
    ):
        try:
            conn.execute(f"ALTER TABLE document_master ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    # Additive migrations for existing DBs (Phase 2.x extraction, Phase 2.3 attachments)
    for col in (
        "body_html TEXT",
        "body_text_raw TEXT",
        "body_text_clean TEXT",
        "body_source_type TEXT",
        "body_has_plain INTEGER",
        "body_has_html INTEGER",
        "full_body_clean TEXT",
        "top_reply_clean TEXT",
        "attachment_count INTEGER",
        "has_attachments INTEGER",
    ):
        try:
            conn.execute(f"ALTER TABLE emails ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    # Optional perf index for GROUP BY / filters on body_source_type (needs column from ALTER loop above).
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emails_body_source_type ON emails(body_source_type)"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()


def insert_email(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    folder: str | None,
    message_id: str | None,
    subject: str | None,
    sender: str | None,
    recipients: str | None,
    date_raw: str | None,
    date_iso: str | None,
    body: str,
    body_html: str = "",
    body_text_raw: str | None = None,
    body_text_clean: str | None = None,
    body_source_type: str | None = None,
    body_has_plain: bool | None = None,
    body_has_html: bool | None = None,
    full_body_clean: str | None = None,
    top_reply_clean: str | None = None,
    attachment_count: int | None = None,
    has_attachments: bool | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO emails
        (source_file, folder, message_id, subject, sender, recipients,
         date_raw, date_iso, body, body_html,
         body_text_raw, body_text_clean, body_source_type, body_has_plain, body_has_html,
         full_body_clean, top_reply_clean, attachment_count, has_attachments)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_file,
            folder,
            message_id,
            subject,
            sender,
            recipients,
            date_raw,
            date_iso,
            body,
            body_html or "",
            body_text_raw or "",
            body_text_clean or "",
            body_source_type or "",
            _bool_to_int(body_has_plain),
            _bool_to_int(body_has_html),
            full_body_clean or "",
            top_reply_clean or "",
            attachment_count if attachment_count is not None else 0,
            _bool_to_int(has_attachments),
        ),
    )
    # Return inserted row id so callers can attach rows in attachments table.
    return cur.lastrowid


def insert_attachment(
    conn: sqlite3.Connection,
    *,
    email_id: int,
    part_index: int,
    filename: str | None,
    content_type: str | None,
    content_disposition: str | None,
    size_bytes: int | None,
    content_id: str | None,
    is_inline: bool | None,
    sha256: str | None,
    saved_path: str | None,
    created_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO attachments
        (email_id, part_index, filename, content_type, content_disposition,
         size_bytes, content_id, is_inline, sha256, saved_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            part_index,
            filename,
            content_type,
            content_disposition,
            size_bytes if size_bytes is not None else 0,
            content_id,
            _bool_to_int(is_inline),
            sha256,
            saved_path,
            created_at,
        ),
    )


def _bool_to_int(v: bool | None) -> int | None:
    """Convert bool to 0/1 for SQLite; None stays None."""
    if v is None:
        return None
    return 1 if v else 0
