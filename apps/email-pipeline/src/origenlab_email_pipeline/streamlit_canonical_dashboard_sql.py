"""Read-only SQLite helpers for Streamlit canonical Gmail (contacto@origenlab.cl) dashboard KPIs."""

from __future__ import annotations

import sqlite3
from typing import Any

from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source


def canonical_emails_where(alias: str | None = None) -> str:
    """Trusted SQL boolean fragment for Workspace Gmail contacto rows."""
    return sql_predicate_contacto_gmail_source(table_alias=alias, coalesce_null=False)


def count_canonical_duplicate_message_id_groups(conn: sqlite3.Connection) -> int | None:
    """Count distinct normalized message_id values that appear more than once (canonical Gmail only)."""
    w = canonical_emails_where()
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT lower(trim(message_id)) AS m
              FROM emails
              WHERE {w}
                AND message_id IS NOT NULL AND trim(message_id) != ''
              GROUP BY m
              HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_missing_message_id(conn: sqlite3.Connection) -> int | None:
    w = canonical_emails_where()
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {w}
              AND (message_id IS NULL OR trim(message_id) = '')
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_missing_date_iso(conn: sqlite3.Connection) -> int | None:
    w = canonical_emails_where()
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {w}
              AND (date_iso IS NULL OR trim(date_iso) = '')
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_empty_body(conn: sqlite3.Connection) -> int | None:
    w = canonical_emails_where()
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {w}
              AND (
                (body IS NULL OR trim(body) = '')
                AND (full_body_clean IS NULL OR trim(full_body_clean) = '')
                AND (top_reply_clean IS NULL OR trim(top_reply_clean) = '')
              )
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_attachments(conn: sqlite3.Connection) -> int | None:
    w = canonical_emails_where("e")
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM attachments a
            JOIN emails e ON e.id = a.email_id
            WHERE {w}
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_sent_inbox(conn: sqlite3.Connection) -> tuple[int | None, int | None]:
    """Approximate (folder heuristics) sent vs inbox counts for canonical Gmail."""
    w = canonical_emails_where()
    try:
        sent_row = conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {w}
              AND (
                lower(coalesce(folder, '')) LIKE '%enviados%'
                OR lower(coalesce(folder, '')) LIKE '%sent%'
              )
            """
        ).fetchone()
        inbox_row = conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {w}
              AND (
                lower(coalesce(folder, '')) LIKE '%inbox%'
                OR lower(trim(coalesce(folder, ''))) = 'inbox'
              )
            """
        ).fetchone()
        return (
            int(sent_row[0]) if sent_row else None,
            int(inbox_row[0]) if inbox_row else None,
        )
    except sqlite3.Error:
        return None, None


def load_inicio_recent_canonical_rows(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Last N canonical Gmail rows for home table (no body blobs)."""
    w = canonical_emails_where()
    lim = max(1, min(int(limit), 50))
    try:
        cur = conn.execute(
            f"""
            SELECT
              id,
              date_iso,
              subject,
              sender,
              folder,
              COALESCE(attachment_count, 0) AS attachment_count
            FROM emails
            WHERE {w}
            ORDER BY
              CASE WHEN date_iso IS NULL OR trim(date_iso) = '' THEN 1 ELSE 0 END,
              date_iso DESC
            LIMIT ?
            """,
            (lim,),
        )
        cols = [d[0] for d in (cur.description or ())]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def fmt_short_date(iso: str | None) -> str:
    if not iso:
        return "—"
    s = str(iso).strip()
    return s[:16] if len(s) > 10 else s


def direction_label_for_folder(folder: str | None) -> str:
    f = (folder or "").lower()
    if "enviados" in f or "sent" in f:
        return "Enviado"
    if "inbox" in f or f.strip() == "inbox":
        return "Recibido"
    if "borrador" in f or "draft" in f:
        return "Borrador"
    if "papelera" in f or "trash" in f:
        return "Papelera"
    return "Otro"


def folder_kind_label(folder: str | None) -> str:
    f = (folder or "").strip()
    if not f:
        return "—"
    if "Enviados" in f:
        return "Enviados"
    if "INBOX" in f or f.lower() == "inbox":
        return "INBOX"
    if "Borrador" in f or "Draft" in f:
        return "Borradores"
    if "Papelera" in f or "Trash" in f:
        return "Papelera"
    return f.split("/")[-1] if "/" in f else f


__all__ = [
    "canonical_emails_where",
    "count_canonical_attachments",
    "count_canonical_duplicate_message_id_groups",
    "count_canonical_empty_body",
    "count_canonical_missing_date_iso",
    "count_canonical_missing_message_id",
    "count_canonical_sent_inbox",
    "direction_label_for_folder",
    "folder_kind_label",
    "fmt_short_date",
    "load_inicio_recent_canonical_rows",
]
