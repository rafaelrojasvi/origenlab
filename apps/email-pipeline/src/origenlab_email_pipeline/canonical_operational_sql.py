"""Read-only SQLite helpers for canonical Gmail (contacto@origenlab.cl) operational KPIs and samples."""

from __future__ import annotations

import sqlite3
from typing import Any

from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.operational_scope import (
    sql_exclude_operational_noise_email,
    sqlite_contact_canonical_link_exists,
    sqlite_opportunity_signal_operational_predicate,
    sqlite_organization_canonical_link_exists,
)


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


def count_canonical_operational_contacts(conn: sqlite3.Connection) -> int | None:
    """Contacts in mart linked to canonical Gmail rows (excludes operational noise)."""
    if not _table_exists(conn, "contact_master") or not _table_exists(conn, "emails"):
        return None
    link = sqlite_contact_canonical_link_exists("cm")
    noise = sql_exclude_operational_noise_email("cm.email")
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM contact_master cm
            WHERE {link}
              AND {noise}
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_operational_organizations(conn: sqlite3.Connection) -> int | None:
    if not _table_exists(conn, "organization_master") or not _table_exists(conn, "emails"):
        return None
    link = sqlite_organization_canonical_link_exists("om")
    noise = sql_exclude_operational_noise_email("om.domain")
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM organization_master om
            WHERE {link}
              AND {noise}
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_operational_opportunity_signals(conn: sqlite3.Connection) -> int | None:
    if not _table_exists(conn, "opportunity_signals") or not _table_exists(conn, "emails"):
        return None
    pred = sqlite_opportunity_signal_operational_predicate("os")
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM opportunity_signals os WHERE {pred}").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_archive_mart_table(conn: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(conn, table):
        return None
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def count_canonical_unique_external_senders(conn: sqlite3.Connection) -> int | None:
    """Distinct non-noise senders on canonical Gmail rows (excluding origenlab/labdelivery)."""
    w = canonical_emails_where()
    noise = sql_exclude_operational_noise_email("sender")
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT lower(trim(sender))) FROM emails
            WHERE {w}
              AND sender IS NOT NULL AND trim(sender) != ''
              AND {noise}
              AND lower(trim(sender)) NOT LIKE '%@origenlab.cl'
              AND lower(trim(sender)) NOT LIKE '%@labdelivery.cl'
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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def load_canonical_gmail_classification_sample(
    conn: sqlite3.Connection,
    *,
    days: int = 120,
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Recent canonical Gmail rows with body fields for heuristic classification (read-only)."""
    d = max(1, min(int(days), 3660))
    lim = max(10, min(int(limit), 10_000))
    day_param = f"-{d} days"
    pred = canonical_emails_where("e")
    if _table_exists(conn, "document_master"):
        doc_sel = (
            "(SELECT group_concat(DISTINCT d.doc_type) "
            "FROM document_master d WHERE d.email_id = e.id) AS doc_types"
        )
    else:
        doc_sel = "NULL AS doc_types"
    sql = f"""
        SELECT
          e.id,
          e.date_iso,
          e.folder,
          e.sender,
          e.recipients,
          e.subject,
          COALESCE(e.body, '') AS body,
          COALESCE(e.full_body_clean, '') AS full_body_clean,
          COALESCE(e.top_reply_clean, '') AS top_reply_clean,
          {doc_sel}
        FROM emails e
        WHERE ({pred})
          AND e.date_iso IS NOT NULL AND trim(e.date_iso) != ''
          AND date(e.date_iso) >= date('now', ?)
        ORDER BY e.date_iso DESC
        LIMIT ?
    """
    try:
        cur = conn.execute(sql, (day_param, lim))
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
    "count_archive_mart_table",
    "count_canonical_attachments",
    "count_canonical_duplicate_message_id_groups",
    "count_canonical_empty_body",
    "count_canonical_missing_date_iso",
    "count_canonical_missing_message_id",
    "count_canonical_operational_contacts",
    "count_canonical_operational_opportunity_signals",
    "count_canonical_operational_organizations",
    "count_canonical_sent_inbox",
    "count_canonical_unique_external_senders",
    "direction_label_for_folder",
    "folder_kind_label",
    "fmt_short_date",
    "load_inicio_recent_canonical_rows",
    "load_canonical_gmail_classification_sample",
]
