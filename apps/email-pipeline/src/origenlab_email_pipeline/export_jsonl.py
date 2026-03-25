"""Stream emails table to JSONL (UTF-8)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson

_PHASE2_SELECT = """
            SELECT id, source_file, folder, message_id, subject, sender, recipients,
                   date_raw, date_iso, body,
                   COALESCE(body_html, '') AS body_html,
                   COALESCE(body_text_raw, '') AS body_text_raw,
                   COALESCE(body_text_clean, '') AS body_text_clean,
                   COALESCE(body_source_type, '') AS body_source_type,
                   COALESCE(body_has_plain, 0) AS body_has_plain,
                   COALESCE(body_has_html, 0) AS body_has_html,
                   COALESCE(full_body_clean, '') AS full_body_clean,
                   COALESCE(top_reply_clean, '') AS top_reply_clean,
                   COALESCE(attachment_count, 0) AS attachment_count,
                   COALESCE(has_attachments, 0) AS has_attachments
            FROM emails
            ORDER BY id
            """


def export_jsonl(db_path: Path, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, source_file, folder, message_id, subject, sender, recipients,
                   date_raw, date_iso, body,
                   COALESCE(body_html, '') AS body_html
            FROM emails
            ORDER BY id
            """
        )
        count = 0
        with out_path.open("wb") as f:
            for row in cur:
                obj = {
                    "id": row["id"],
                    "source_file": row["source_file"],
                    "folder": row["folder"],
                    "message_id": row["message_id"],
                    "subject": row["subject"],
                    "sender": row["sender"],
                    "recipients": row["recipients"],
                    "date_raw": row["date_raw"],
                    "date_iso": row["date_iso"],
                    "body": row["body"],
                    "body_html": row["body_html"],
                }
                f.write(orjson.dumps(obj, option=orjson.OPT_APPEND_NEWLINE))
                count += 1
        return count
    finally:
        conn.close()


def export_jsonl_with_phase2(db_path: Path, out_path: Path) -> int:
    """Like export_jsonl but includes Phase 2.1/2.2 body fields and attachment counters."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(_PHASE2_SELECT)
        count = 0
        with out_path.open("wb") as f:
            for row in cur:
                obj = {
                    "id": row["id"],
                    "source_file": row["source_file"],
                    "folder": row["folder"],
                    "message_id": row["message_id"],
                    "subject": row["subject"],
                    "sender": row["sender"],
                    "recipients": row["recipients"],
                    "date_raw": row["date_raw"],
                    "date_iso": row["date_iso"],
                    "body": row["body"],
                    "body_html": row["body_html"],
                    "body_text_raw": row["body_text_raw"],
                    "body_text_clean": row["body_text_clean"],
                    "body_source_type": row["body_source_type"],
                    "body_has_plain": row["body_has_plain"],
                    "body_has_html": row["body_has_html"],
                    "full_body_clean": row["full_body_clean"],
                    "top_reply_clean": row["top_reply_clean"],
                    "attachment_count": row["attachment_count"],
                    "has_attachments": row["has_attachments"],
                }
                f.write(orjson.dumps(obj, option=orjson.OPT_APPEND_NEWLINE))
                count += 1
        return count
    finally:
        conn.close()
