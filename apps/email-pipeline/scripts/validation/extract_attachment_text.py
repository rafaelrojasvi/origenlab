#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Can DELETE FROM attachment_extracts (e.g. force / redo paths).
# Mutates SQLite extract tables; review flags before running on production DB copies.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Phase 2.4: post-pass attachment text extraction into SQLite.

Workflow:
- Uses existing `emails.source_file` (mbox path) and `emails.message_id` to re-open mbox files.
- Matches MIME parts to `attachments` rows by sha256 (preferred) and falls back to part_index.
- Writes one row per attachment into `attachment_extracts` (idempotent; use --force to redo).

No OCR. Large text is truncated.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from email.header import decode_header

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.attachment_extract import extract_bytes, guess_method
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect, init_schema
from origenlab_email_pipeline.parse_mbox import open_mbox
from origenlab_email_pipeline.progress import iter_with_progress


def _header_to_str(v) -> str:
    """Best-effort conversion of mailbox/email header values to a plain string."""
    if v is None:
        return ""
    if isinstance(v, str):
        s = v
    else:
        # mailbox.mbox can return email.header.Header objects here.
        s = str(v)
    # Decode encoded-word if present.
    if "=?" in s:
        try:
            parts = decode_header(s)
            out: list[str] = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    out.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    out.append(part or "")
            s = "".join(out)
        except Exception:
            pass
    return s.strip()


def _is_noise_attachment(content_type: str | None) -> bool:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return True
    if ct in ("message/delivery-status", "text/rfc822-headers"):
        return True
    if ct.startswith("multipart/") and (ct.endswith("report") or ct == "multipart/report"):
        return True
    return False


def _is_candidate(att: dict, *, only: str | None) -> bool:
    if att.get("is_inline") == 1:
        return False
    if (att.get("size_bytes") or 0) <= 0:
        return False
    if _is_noise_attachment(att.get("content_type")):
        return False
    m = guess_method(att.get("content_type"), att.get("filename"))
    if m == "none":
        return False
    if only and m != only:
        return False
    return True


def _existing_extracts(conn: sqlite3.Connection) -> set[int]:
    try:
        rows = conn.execute("SELECT attachment_id FROM attachment_extracts").fetchall()
        return {int(r[0]) for r in rows}
    except sqlite3.OperationalError:
        return set()


def _load_targets(conn: sqlite3.Connection, *, only: str | None, limit: int | None) -> tuple[
    dict[str, dict[str, dict]], dict[int, dict]
]:
    """
    Returns:
    - by_mbox_then_msgid: {source_file: {message_id: {att_id: att_row}}}
    - by_attachment_id: {att_id: att_row}
    """
    existing = _existing_extracts(conn)
    sql = """
        SELECT
          a.id, a.email_id, a.part_index, a.filename, a.content_type, a.content_disposition,
          a.size_bytes, a.content_id, a.is_inline, a.sha256,
          e.source_file, e.message_id
        FROM attachments a
        JOIN emails e ON e.id = a.email_id
        WHERE 1=1
    """
    params: list[object] = []
    if limit is not None:
        # Apply limit after filtering in Python (SQLite LIMIT would bias by join order).
        pass

    rows = conn.execute(sql, params).fetchall()
    by_mbox_then_msgid: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    by_attachment_id: dict[int, dict] = {}
    picked = 0
    for r in rows:
        att = {
            "id": int(r[0]),
            "email_id": int(r[1]),
            "part_index": int(r[2]),
            "filename": r[3],
            "content_type": r[4],
            "content_disposition": r[5],
            "size_bytes": int(r[6] or 0),
            "content_id": r[7],
            "is_inline": int(r[8] or 0),
            "sha256": r[9],
            "source_file": r[10],
            "message_id": (r[11] or "").strip(),
        }
        if not att["message_id"]:
            continue
        if not _is_candidate(att, only=only):
            continue
        if att["id"] in existing:
            continue
        by_mbox_then_msgid[att["source_file"]][att["message_id"]][att["id"]] = att
        by_attachment_id[att["id"]] = att
        picked += 1
        if limit is not None and picked >= limit:
            break
    return by_mbox_then_msgid, by_attachment_id


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _insert_extract(conn: sqlite3.Connection, *, attachment_id: int, res) -> None:
    conn.execute(
        """
        INSERT INTO attachment_extracts
        (attachment_id, extract_status, extract_method, text_preview, text_truncated, char_count,
         page_count, sheet_count, detected_doc_type,
         has_quote_terms, has_invoice_terms, has_price_list_terms, has_purchase_terms,
         error_message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(attachment_id) DO UPDATE SET
          extract_status=excluded.extract_status,
          extract_method=excluded.extract_method,
          text_preview=excluded.text_preview,
          text_truncated=excluded.text_truncated,
          char_count=excluded.char_count,
          page_count=excluded.page_count,
          sheet_count=excluded.sheet_count,
          detected_doc_type=excluded.detected_doc_type,
          has_quote_terms=excluded.has_quote_terms,
          has_invoice_terms=excluded.has_invoice_terms,
          has_price_list_terms=excluded.has_price_list_terms,
          has_purchase_terms=excluded.has_purchase_terms,
          error_message=excluded.error_message,
          created_at=excluded.created_at
        """,
        (
            attachment_id,
            res.status,
            res.method,
            res.text_preview,
            res.text_truncated,
            res.char_count,
            res.page_count,
            res.sheet_count,
            res.detected_doc_type,
            1 if res.has_quote_terms else 0 if res.has_quote_terms is not None else None,
            1 if res.has_invoice_terms else 0 if res.has_invoice_terms is not None else None,
            1 if res.has_price_list_terms else 0 if res.has_price_list_terms is not None else None,
            1 if res.has_purchase_terms else 0 if res.has_purchase_terms is not None else None,
            res.error_message,
            res.created_at,
        ),
    )


def _mark_skipped(conn: sqlite3.Connection, *, attachment_id: int, method: str, error: str) -> None:
    conn.execute(
        """
        INSERT INTO attachment_extracts
        (attachment_id, extract_status, extract_method, text_preview, text_truncated, char_count,
         error_message, created_at)
        VALUES (?, 'skipped', ?, '', '', 0, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        ON CONFLICT(attachment_id) DO UPDATE SET
          extract_status='skipped',
          extract_method=excluded.extract_method,
          text_preview='',
          text_truncated='',
          char_count=0,
          error_message=excluded.error_message,
          created_at=excluded.created_at
        """,
        (attachment_id, method, error[:500]),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-extract even if already present")
    ap.add_argument("--limit", type=int, default=None, help="limit number of attachments processed")
    ap.add_argument(
        "--only",
        choices=["pdf_text", "docx", "xlsx", "csv", "xml"],
        default=None,
        help="only extract a single method (debug)",
    )
    ap.add_argument("--commit-every", type=int, default=200, help="commit every N inserts")
    args = ap.parse_args()

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()

    conn = connect(db_path)
    init_schema(conn)

    if args.force:
        conn.execute("DELETE FROM attachment_extracts")
        conn.commit()

    by_mbox_then_msgid, by_attachment_id = _load_targets(conn, only=args.only, limit=args.limit)
    mboxes = list(by_mbox_then_msgid.keys())
    total_targets = len(by_attachment_id)

    print(f"DB: {db_path}")
    print(f"Targets: {total_targets} attachments across {len(mboxes)} mbox files")

    inserted = 0
    missing = 0
    processed = 0

    for mbox_path in iter_with_progress(mboxes, desc="mbox files"):
        mbox = open_mbox(mbox_path)
        if mbox is None:
            # mark all attachments under this mbox as skipped
            for msgid, att_map in by_mbox_then_msgid[mbox_path].items():
                for att_id, att in att_map.items():
                    _mark_skipped(conn, attachment_id=att_id, method=guess_method(att["content_type"], att["filename"]), error="mbox open failed")
                    missing += 1
            conn.commit()
            continue

        targets_for_mbox = by_mbox_then_msgid[mbox_path]
        msgid_set = set(targets_for_mbox.keys())

        try:
            for msg in mbox:
                msgid = _header_to_str(msg.get("Message-ID"))
                if not msgid or msgid not in msgid_set:
                    continue

                att_rows = targets_for_mbox[msgid]  # {att_id: att_row}
                expected_by_sha = {att["sha256"]: att_id for att_id, att in att_rows.items() if att.get("sha256")}
                expected_by_part = {att["part_index"]: att_id for att_id, att in att_rows.items()}

                # Walk non-body MIME parts and compute sha256 if decodable.
                part_index = 0
                found_ids: set[int] = set()
                for part in msg.walk():
                    ctype = (part.get_content_type() or "").lower()
                    disp = str(part.get("Content-Disposition") or "").lower()
                    if ctype.startswith("text/") and ("attachment" not in disp):
                        continue
                    payload = part.get_payload(decode=True)
                    if not isinstance(payload, (bytes, bytearray)) or not payload:
                        part_index += 1
                        continue
                    sha = _hash_bytes(payload)

                    att_id = expected_by_sha.get(sha)
                    if att_id is None:
                        att_id = expected_by_part.get(part_index)
                    if att_id is None:
                        part_index += 1
                        continue

                    att = by_attachment_id.get(att_id)
                    if not att:
                        part_index += 1
                        continue

                    res = extract_bytes(
                        bytes(payload),
                        content_type=att.get("content_type"),
                        filename=att.get("filename"),
                    )
                    _insert_extract(conn, attachment_id=att_id, res=res)
                    inserted += 1
                    processed += 1
                    found_ids.add(att_id)
                    if inserted % max(1, int(args.commit_every)) == 0:
                        conn.commit()
                    part_index += 1

                # Any attachment targets for this Message-ID that we didn't find in MIME
                for att_id in att_rows.keys():
                    if att_id not in found_ids:
                        att = by_attachment_id.get(att_id)
                        _mark_skipped(
                            conn,
                            attachment_id=att_id,
                            method=guess_method(att.get("content_type"), att.get("filename")) if att else "none",
                            error="attachment payload not found in mbox message",
                        )
                        missing += 1
                        processed += 1
                if processed % max(1, int(args.commit_every)) == 0:
                    conn.commit()
        finally:
            mbox.close()

    conn.commit()
    conn.close()
    print(f"Inserted/updated extracts: {inserted}")
    print(f"Marked skipped (not found / mbox open failed): {missing}")


if __name__ == "__main__":
    main()

