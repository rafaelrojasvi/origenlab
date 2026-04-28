#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Writes to Postgres; --replace TRUNCATEs archive.* target
# tables before reload. Wrong target URL causes data loss on the wrong database.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Copy SQLite archive tables into Postgres archive.* (Alembic 20260419_0002).

SQLite stays read-only; source must pass strict validation (see validate_sqlite_archive_for_postgres).

Memory / large archives:
    Use a small ``--batch-size`` (default 500). Each batch is converted, inserted, and committed;
    only one batch of rows + TEXT bodies lives in Python at a time.

Commits:
    Loads use **per-batch commits** (not one giant transaction). If the process stops mid-run,
    Postgres may contain **partial** archive rows. Rerun with ``--replace`` to truncate
    archive tables child-first and reload from scratch.

Dry-run:
    Connects and validates only; does not write to Postgres.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INTERRUPTED_LOAD_HINT = (
    "Per-batch commits: an interrupted run may leave partial rows in archive.*. "
    "Rerun with --replace to truncate child-first and reload."
)

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings

_VALIDATE_PATH = REPO / "scripts" / "qa" / "validate_sqlite_archive_for_postgres.py"
_spec = importlib.util.spec_from_file_location("validate_sqlite_archive_for_postgres", _VALIDATE_PATH)
assert _spec and _spec.loader
_validate_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate_mod)
_connect_readonly = _validate_mod._connect_readonly
build_report = _validate_mod.build_report
_normalize_iso_z = _validate_mod._normalize_iso_z

try:
    import psycopg
except ImportError as exc:  # pragma: no cover - exercised when postgres extra missing
    psycopg = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

GMAIL_SENT_FOLDERS = ("[Gmail]/Enviados", "[Gmail]/Sent Mail")
# Bound as query parameters — never embed "gmail:%" in psycopg SQL literals (% is placeholder syntax).
GMAIL_SOURCE_LIKE_PATTERN = "gmail:%"


class ConversionError(Exception):
    """Invalid cell value during SQLite → Postgres conversion."""

    def __init__(self, table: str, row_id: Any, column: str, value: Any) -> None:
        self.table = table
        self.row_id = row_id
        self.column = column
        self.value = value
        super().__init__(
            f"invalid conversion {table} id={row_id!r} column={column!r} value={value!r}"
        )


def normalize_postgres_url(url: str) -> str:
    """Strip SQLAlchemy driver suffix so psycopg can connect."""
    u = url.strip()
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if u.startswith(prefix):
            return "postgresql://" + u[len(prefix) :]
    return u


def resolve_sqlite_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = (os.environ.get("ORIGENLAB_SQLITE_PATH") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return load_settings().resolved_sqlite_path()


def resolve_postgres_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return normalize_postgres_url(explicit.strip())
    for key in ("ORIGENLAB_POSTGRES_URL", "ALEMBIC_DATABASE_URL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return normalize_postgres_url(v)
    raise ValueError(
        "Postgres URL required. Pass --postgres-url or set ORIGENLAB_POSTGRES_URL "
        "or ALEMBIC_DATABASE_URL."
    )


def iso_text_to_datetime(value: Any) -> datetime | None:
    """SQLite TEXT -> aware datetime for TIMESTAMPTZ. NULL unchanged."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected str or NULL")
    s = _normalize_iso_z(value.strip())
    if not s:
        raise ValueError("empty timestamp string")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def int_to_bool_or_none(value: Any, *, table: str, row_id: Any, column: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConversionError(table, row_id, column, value)
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ConversionError(table, row_id, column, value)


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            "psycopg is required for this script. Install the postgres group: "
            f"uv sync --group postgres ({_PSYCOPG_IMPORT_ERROR})"
        )


def archive_table_exists(cur: psycopg.Cursor, schema: str, name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, name),
    )
    return cur.fetchone() is not None


def assert_archive_schema_ready(cur: psycopg.Cursor) -> None:
    missing = []
    for t in ("emails", "attachments", "attachment_extracts"):
        if not archive_table_exists(cur, "archive", t):
            missing.append(f"archive.{t}")
    if missing:
        raise ValueError(
            "Postgres archive tables missing (run Alembic to at least 20260419_0002): "
            + ", ".join(missing)
        )


def pg_archive_counts(cur: psycopg.Cursor) -> dict[str, int]:
    q = {
        "emails": "SELECT COUNT(*) FROM archive.emails",
        "attachments": "SELECT COUNT(*) FROM archive.attachments",
        "attachment_extracts": "SELECT COUNT(*) FROM archive.attachment_extracts",
    }
    out: dict[str, int] = {}
    for t in ("emails", "attachments", "attachment_extracts"):
        cur.execute(q[t])
        out[t] = int(cur.fetchone()[0])
    return out


def truncate_archive_child_first(cur: psycopg.Cursor) -> None:
    cur.execute(
        "TRUNCATE archive.attachment_extracts, archive.attachments, archive.emails RESTART IDENTITY"
    )


def reset_sequence(cur: psycopg.Cursor, *, table_sql: str, id_column: str) -> None:
    cur.execute(
        "SELECT pg_get_serial_sequence(%s, %s)",
        (table_sql, id_column),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"no serial sequence for {table_sql}.{id_column}")
    seq = row[0]
    cur.execute(f"SELECT COALESCE(MAX({id_column}), 0) FROM {table_sql}")
    max_id = int(cur.fetchone()[0])
    if max_id == 0:
        cur.execute("SELECT setval(%s, 1, false)", (seq,))
    else:
        cur.execute("SELECT setval(%s, %s, true)", (seq, max_id))


def sqlite_quality_metrics(conn: sqlite3.Connection) -> dict[str, int]:
    dup_extra = int(
        conn.execute(
            """
            SELECT COALESCE(SUM(cnt - 1), 0)
            FROM (
              SELECT COUNT(*) AS cnt
              FROM emails
              WHERE message_id IS NOT NULL AND TRIM(message_id) != ''
              GROUP BY message_id
              HAVING COUNT(*) > 1
            ) t
            """
        ).fetchone()[0]
    )
    gmail_sent = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM emails
            WHERE source_file LIKE ?
              AND folder IN (?, ?)
            """,
            (GMAIL_SOURCE_LIKE_PATTERN, *GMAIL_SENT_FOLDERS),
        ).fetchone()[0]
    )
    return {"duplicate_non_null_message_id_extra_rows": dup_extra, "gmail_sent_rows": gmail_sent}


def pg_quality_metrics(cur: psycopg.Cursor) -> dict[str, int]:
    cur.execute(
        """
        SELECT COALESCE(SUM(cnt - 1), 0)
        FROM (
          SELECT COUNT(*) AS cnt
          FROM archive.emails
          WHERE message_id IS NOT NULL AND TRIM(message_id) <> ''
          GROUP BY message_id
          HAVING COUNT(*) > 1
        ) t
        """
    )
    dup_extra = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM archive.emails
        WHERE source_file LIKE %s
          AND folder IN (%s, %s)
        """,
        (GMAIL_SOURCE_LIKE_PATTERN, *GMAIL_SENT_FOLDERS),
    )
    gmail_sent = int(cur.fetchone()[0])
    return {"duplicate_non_null_message_id_extra_rows": dup_extra, "gmail_sent_rows": gmail_sent}


def sqlite_id_ranges(conn: sqlite3.Connection) -> dict[str, tuple[int | None, int | None]]:
    out: dict[str, tuple[int | None, int | None]] = {}
    for table, col in (
        ("emails", "id"),
        ("attachments", "id"),
        ("attachment_extracts", "id"),
    ):
        r = conn.execute(
            f"SELECT MIN({col}), MAX({col}) FROM {table}"
        ).fetchone()
        lo = int(r[0]) if r[0] is not None else None
        hi = int(r[1]) if r[1] is not None else None
        out[table] = (lo, hi)
    return out


def pg_id_ranges(cur: psycopg.Cursor) -> dict[str, tuple[int | None, int | None]]:
    qmap = {
        "emails": "SELECT MIN(id), MAX(id) FROM archive.emails",
        "attachments": "SELECT MIN(id), MAX(id) FROM archive.attachments",
        "attachment_extracts": "SELECT MIN(id), MAX(id) FROM archive.attachment_extracts",
    }
    out: dict[str, tuple[int | None, int | None]] = {}
    for k, sql in qmap.items():
        cur.execute(sql)
        lo, hi = cur.fetchone()
        out[k] = (
            int(lo) if lo is not None else None,
            int(hi) if hi is not None else None,
        )
    return out


def count_pg_orphans(cur: psycopg.Cursor) -> dict[str, int]:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM archive.attachments a
        WHERE NOT EXISTS (SELECT 1 FROM archive.emails e WHERE e.id = a.email_id)
        """
    )
    att = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM archive.attachment_extracts x
        WHERE NOT EXISTS (SELECT 1 FROM archive.attachments a WHERE a.id = x.attachment_id)
        """
    )
    ext = int(cur.fetchone()[0])
    return {"attachments_missing_email": att, "attachment_extracts_missing_attachment": ext}


def load_emails_batch(
    sconn: sqlite3.Connection,
    *,
    last_id: int,
    batch_size: int,
) -> list[tuple[Any, ...]]:
    return sconn.execute(
        """
        SELECT id, source_file, folder, message_id, subject, sender, recipients, date_raw, date_iso,
               body, body_html, body_text_raw, body_text_clean, body_source_type,
               body_has_plain, body_has_html, full_body_clean, top_reply_clean,
               attachment_count, has_attachments
        FROM emails
        WHERE id > ?
        ORDER BY id
        LIMIT ?
        """,
        (last_id, batch_size),
    ).fetchall()


def row_to_email_tuple(row: tuple[Any, ...]) -> tuple[Any, ...]:
    (
        rid,
        source_file,
        folder,
        message_id,
        subject,
        sender,
        recipients,
        date_raw,
        date_iso,
        body,
        body_html,
        body_text_raw,
        body_text_clean,
        body_source_type,
        body_has_plain,
        body_has_html,
        full_body_clean,
        top_reply_clean,
        attachment_count,
        has_attachments,
    ) = row
    try:
        dti = iso_text_to_datetime(date_iso)
    except ValueError:
        raise ConversionError("emails", rid, "date_iso", date_iso) from None
    try:
        b1 = int_to_bool_or_none(body_has_plain, table="emails", row_id=rid, column="body_has_plain")
        b2 = int_to_bool_or_none(body_has_html, table="emails", row_id=rid, column="body_has_html")
        b3 = int_to_bool_or_none(has_attachments, table="emails", row_id=rid, column="has_attachments")
    except ConversionError:
        raise
    return (
        rid,
        source_file,
        folder,
        message_id,
        subject,
        sender,
        recipients,
        date_raw,
        dti,
        body,
        body_html,
        body_text_raw,
        body_text_clean,
        body_source_type,
        b1,
        b2,
        full_body_clean,
        top_reply_clean,
        attachment_count,
        b3,
    )


def load_attachments_batch(
    sconn: sqlite3.Connection, *, last_id: int, batch_size: int
) -> list[tuple[Any, ...]]:
    return sconn.execute(
        """
        SELECT id, email_id, part_index, filename, content_type, content_disposition,
               size_bytes, content_id, is_inline, sha256, saved_path, created_at
        FROM attachments
        WHERE id > ?
        ORDER BY id
        LIMIT ?
        """,
        (last_id, batch_size),
    ).fetchall()


def row_to_attachment_tuple(row: tuple[Any, ...]) -> tuple[Any, ...]:
    (
        rid,
        email_id,
        part_index,
        filename,
        content_type,
        content_disposition,
        size_bytes,
        content_id,
        is_inline,
        sha256,
        saved_path,
        created_at,
    ) = row
    try:
        cat = iso_text_to_datetime(created_at)
    except ValueError as exc:
        raise ConversionError("attachments", rid, "created_at", created_at) from exc
    ib = int_to_bool_or_none(is_inline, table="attachments", row_id=rid, column="is_inline")
    sb = None if size_bytes is None else int(size_bytes)
    return (
        rid,
        int(email_id),
        int(part_index),
        filename,
        content_type,
        content_disposition,
        sb,
        content_id,
        ib,
        sha256,
        saved_path,
        cat,
    )


def load_extracts_batch(
    sconn: sqlite3.Connection, *, last_id: int, batch_size: int
) -> list[tuple[Any, ...]]:
    return sconn.execute(
        """
        SELECT id, attachment_id, extract_status, extract_method, text_preview, text_truncated,
               char_count, page_count, sheet_count, detected_doc_type,
               has_quote_terms, has_invoice_terms, has_price_list_terms, has_purchase_terms,
               error_message, created_at
        FROM attachment_extracts
        WHERE id > ?
        ORDER BY id
        LIMIT ?
        """,
        (last_id, batch_size),
    ).fetchall()


def row_to_extract_tuple(row: tuple[Any, ...]) -> tuple[Any, ...]:
    (
        rid,
        attachment_id,
        extract_status,
        extract_method,
        text_preview,
        text_truncated,
        char_count,
        page_count,
        sheet_count,
        detected_doc_type,
        has_quote_terms,
        has_invoice_terms,
        has_price_list_terms,
        has_purchase_terms,
        error_message,
        created_at,
    ) = row
    try:
        cat = iso_text_to_datetime(created_at)
    except ValueError as exc:
        raise ConversionError("attachment_extracts", rid, "created_at", created_at) from exc
    return (
        rid,
        int(attachment_id),
        extract_status,
        extract_method,
        text_preview,
        text_truncated,
        char_count,
        page_count,
        sheet_count,
        detected_doc_type,
        int_to_bool_or_none(has_quote_terms, table="attachment_extracts", row_id=rid, column="has_quote_terms"),
        int_to_bool_or_none(
            has_invoice_terms, table="attachment_extracts", row_id=rid, column="has_invoice_terms"
        ),
        int_to_bool_or_none(
            has_price_list_terms, table="attachment_extracts", row_id=rid, column="has_price_list_terms"
        ),
        int_to_bool_or_none(
            has_purchase_terms, table="attachment_extracts", row_id=rid, column="has_purchase_terms"
        ),
        error_message,
        cat,
    )


INSERT_EMAILS = """
INSERT INTO archive.emails (
  id, source_file, folder, message_id, subject, sender, recipients, date_raw, date_iso,
  body, body_html, body_text_raw, body_text_clean, body_source_type,
  body_has_plain, body_has_html, full_body_clean, top_reply_clean,
  attachment_count, has_attachments
) VALUES (
  %s, %s, %s, %s, %s, %s, %s, %s, %s,
  %s, %s, %s, %s, %s,
  %s, %s, %s, %s,
  %s, %s
)
"""

INSERT_ATTACHMENTS = """
INSERT INTO archive.attachments (
  id, email_id, part_index, filename, content_type, content_disposition,
  size_bytes, content_id, is_inline, sha256, saved_path, created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_EXTRACTS = """
INSERT INTO archive.attachment_extracts (
  id, attachment_id, extract_status, extract_method, text_preview, text_truncated,
  char_count, page_count, sheet_count, detected_doc_type,
  has_quote_terms, has_invoice_terms, has_price_list_terms, has_purchase_terms,
  error_message, created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def format_load_progress(
    *,
    pg_table: str,
    loaded_so_far: int,
    total: int,
    elapsed_s: float,
    batch_len: int,
) -> str:
    """Single-line progress for stderr (no row payloads)."""
    pct = (100.0 * loaded_so_far / total) if total else 0.0
    return (
        f"loading {pg_table}: {loaded_so_far}/{total} ({pct:.1f}%) "
        f"elapsed={elapsed_s:.1f}s batch={batch_len}"
    )


def migrate_table_emails(
    sconn: sqlite3.Connection,
    pconn: psycopg.Connection,
    loaded: dict[str, int],
    *,
    batch_size: int,
    total_rows: int,
    t_load_start: float,
) -> None:
    last_id = 0
    key = "emails"
    pg_name = "archive.emails"
    while True:
        rows = load_emails_batch(sconn, last_id=last_id, batch_size=batch_size)
        if not rows:
            break
        batch_len = len(rows)
        last_row_id = int(rows[-1][0])
        try:
            batch: list[tuple[Any, ...]] = []
            for r in rows:
                batch.append(row_to_email_tuple(r))
            with pconn.cursor() as cur:
                cur.executemany(INSERT_EMAILS, batch)
            pconn.commit()
        finally:
            del rows
            del batch
            gc.collect()

        loaded[key] = loaded.get(key, 0) + batch_len
        elapsed = time.monotonic() - t_load_start
        print(
            format_load_progress(
                pg_table=pg_name,
                loaded_so_far=loaded[key],
                total=total_rows,
                elapsed_s=elapsed,
                batch_len=batch_len,
            ),
            flush=True,
        )
        last_id = last_row_id


def migrate_table_attachments(
    sconn: sqlite3.Connection,
    pconn: psycopg.Connection,
    loaded: dict[str, int],
    *,
    batch_size: int,
    total_rows: int,
    t_load_start: float,
) -> None:
    last_id = 0
    key = "attachments"
    pg_name = "archive.attachments"
    while True:
        rows = load_attachments_batch(sconn, last_id=last_id, batch_size=batch_size)
        if not rows:
            break
        batch_len = len(rows)
        last_row_id = int(rows[-1][0])
        try:
            batch = [row_to_attachment_tuple(r) for r in rows]
            with pconn.cursor() as cur:
                cur.executemany(INSERT_ATTACHMENTS, batch)
            pconn.commit()
        finally:
            del rows
            del batch

        loaded[key] = loaded.get(key, 0) + batch_len
        elapsed = time.monotonic() - t_load_start
        print(
            format_load_progress(
                pg_table=pg_name,
                loaded_so_far=loaded[key],
                total=total_rows,
                elapsed_s=elapsed,
                batch_len=batch_len,
            ),
            flush=True,
        )
        last_id = last_row_id


def migrate_table_extracts(
    sconn: sqlite3.Connection,
    pconn: psycopg.Connection,
    loaded: dict[str, int],
    *,
    batch_size: int,
    total_rows: int,
    t_load_start: float,
) -> None:
    last_id = 0
    key = "attachment_extracts"
    pg_name = "archive.attachment_extracts"
    while True:
        rows = load_extracts_batch(sconn, last_id=last_id, batch_size=batch_size)
        if not rows:
            break
        batch_len = len(rows)
        last_row_id = int(rows[-1][0])
        try:
            batch = [row_to_extract_tuple(r) for r in rows]
            with pconn.cursor() as cur:
                cur.executemany(INSERT_EXTRACTS, batch)
            pconn.commit()
        finally:
            del rows
            del batch

        loaded[key] = loaded.get(key, 0) + batch_len
        elapsed = time.monotonic() - t_load_start
        print(
            format_load_progress(
                pg_table=pg_name,
                loaded_so_far=loaded[key],
                total=total_rows,
                elapsed_s=elapsed,
                batch_len=batch_len,
            ),
            flush=True,
        )
        last_id = last_row_id


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None, help="SQLite path (else env/settings)")
    p.add_argument("--postgres-url", default=None, help="Postgres URL (else ORIGENLAB_POSTGRES_URL / ALEMBIC_DATABASE_URL)")
    p.add_argument(
        "--batch-size",
        type=int,
        default=500,
        metavar="N",
        help="Rows per batch (default 500; use smaller values for huge email bodies / low RAM)",
    )
    p.add_argument("--replace", action="store_true", help="Truncate archive tables (child-first) before load")
    p.add_argument("--dry-run", action="store_true", help="Validate and inspect only; no writes")
    p.add_argument("--json-out", type=Path, default=None, help="Write JSON summary")
    p.add_argument("--sample-limit", type=int, default=10, metavar="N", help="Passed to strict validation")
    return p


def _empty_result() -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": False,
        "replace": False,
        "batch_size": None,
        "elapsed_seconds": None,
        "sqlite_counts": {},
        "postgres_counts_before": {},
        "postgres_counts_after": {},
        "loaded": {},
        "validation": {},
        "errors": [],
        "warnings": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_limit = max(1, int(args.sample_limit))
    batch_size = max(1, int(args.batch_size))

    result: dict[str, Any] = _empty_result()
    result["dry_run"] = bool(args.dry_run)
    result["replace"] = bool(args.replace)

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    if not sqlite_path.is_file():
        result["errors"].append(f"SQLite file not found: {sqlite_path}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    try:
        sconn = _connect_readonly(sqlite_path)
    except sqlite3.Error as exc:
        result["errors"].append(f"SQLite open failed: {exc}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    try:
        vreport = build_report(sconn, sample_limit=sample_limit)
    except RuntimeError as exc:
        sconn.close()
        result["errors"].append(str(exc))
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    result["sqlite_counts"] = {k: v for k, v in vreport["counts"].items() if k != "document_master" and v is not None}
    if not vreport["ok"]:
        result["errors"].append(
            "SQLite archive failed strict validation: " + ", ".join(vreport.get("strict_reasons", []))
        )
        sconn.close()
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 1

    try:
        pg_url = resolve_postgres_url(args.postgres_url)
    except ValueError as exc:
        sconn.close()
        result["errors"].append(f"error: {exc}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    try:
        _require_psycopg()
    except RuntimeError as exc:
        sconn.close()
        result["errors"].append(str(exc))
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    assert psycopg is not None

    try:
        pconn = psycopg.connect(pg_url, autocommit=False)
    except Exception as exc:  # noqa: BLE001
        sconn.close()
        result["errors"].append(f"Postgres connect failed: {exc}")
        _write_json(args.json_out, result)
        print(result["errors"][-1], file=sys.stderr)
        return 2

    try:
        with pconn.cursor() as cur:
            try:
                assert_archive_schema_ready(cur)
            except ValueError as exc:
                pconn.rollback()
                sconn.close()
                result["errors"].append(f"error: {exc}")
                _write_json(args.json_out, result)
                print(result["errors"][-1], file=sys.stderr)
                return 2
            before = pg_archive_counts(cur)
        result["postgres_counts_before"] = dict(before)

        nonempty = any(c > 0 for c in before.values())
        if nonempty and not args.replace and not args.dry_run:
            result["errors"].append(
                "Postgres archive tables are not empty. Use --replace to truncate and reload, or clear manually."
            )
            pconn.rollback()
            sconn.close()
            _write_json(args.json_out, result)
            print(result["errors"][-1], file=sys.stderr)
            return 1

        result["batch_size"] = batch_size

        if args.dry_run:
            pconn.rollback()
            sconn.close()
            result["ok"] = True
            result["validation"] = {
                "note": "dry_run: no data written",
                "sqlite_strict_ok": True,
                "postgres_archive_empty_or_replace": not nonempty or args.replace,
            }
            _write_json(args.json_out, result)
            print("dry-run ok: validation passed; no writes performed.")
            return 0

        if args.replace and nonempty:
            with pconn.cursor() as cur:
                truncate_archive_child_first(cur)
            pconn.commit()

        loaded: dict[str, int] = {"emails": 0, "attachments": 0, "attachment_extracts": 0}
        t_load_start = time.monotonic()
        try:
            migrate_table_emails(
                sconn,
                pconn,
                loaded,
                batch_size=batch_size,
                total_rows=int(vreport["counts"]["emails"] or 0),
                t_load_start=t_load_start,
            )
            migrate_table_attachments(
                sconn,
                pconn,
                loaded,
                batch_size=batch_size,
                total_rows=int(vreport["counts"]["attachments"] or 0),
                t_load_start=t_load_start,
            )
            migrate_table_extracts(
                sconn,
                pconn,
                loaded,
                batch_size=batch_size,
                total_rows=int(vreport["counts"]["attachment_extracts"] or 0),
                t_load_start=t_load_start,
            )
        except ConversionError as exc:
            result["loaded"] = dict(loaded)
            result["elapsed_seconds"] = round(time.monotonic() - t_load_start, 3)
            result["warnings"].append(INTERRUPTED_LOAD_HINT)
            result["errors"].append(str(exc))
            sconn.close()
            _write_json(args.json_out, result)
            print(str(exc), file=sys.stderr)
            return 1

        result["loaded"] = dict(loaded)
        result["elapsed_seconds"] = round(time.monotonic() - t_load_start, 3)

        with pconn.cursor() as cur:
            reset_sequence(cur, table_sql="archive.emails", id_column="id")
            reset_sequence(cur, table_sql="archive.attachments", id_column="id")
            reset_sequence(cur, table_sql="archive.attachment_extracts", id_column="id")

            after = pg_archive_counts(cur)
            result["postgres_counts_after"] = dict(after)

            sq = sqlite_quality_metrics(sconn)
            pq = pg_quality_metrics(cur)
            srange = sqlite_id_ranges(sconn)
            prange = pg_id_ranges(cur)
            orphans = count_pg_orphans(cur)

            val_ok = (
                after["emails"] == vreport["counts"]["emails"]
                and after["attachments"] == vreport["counts"]["attachments"]
                and after["attachment_extracts"] == vreport["counts"]["attachment_extracts"]
                and srange == prange
                and sq["duplicate_non_null_message_id_extra_rows"] == pq["duplicate_non_null_message_id_extra_rows"]
                and sq["gmail_sent_rows"] == pq["gmail_sent_rows"]
                and orphans["attachments_missing_email"] == 0
                and orphans["attachment_extracts_missing_attachment"] == 0
            )

            result["validation"] = {
                "row_counts_match": {
                    "emails": after["emails"] == vreport["counts"]["emails"],
                    "attachments": after["attachments"] == vreport["counts"]["attachments"],
                    "attachment_extracts": after["attachment_extracts"] == vreport["counts"]["attachment_extracts"],
                },
                "min_max_ids_match": {k: {"sqlite": srange[k], "postgres": prange[k]} for k in srange},
                "duplicate_message_id_extra_rows": {
                    "sqlite": sq["duplicate_non_null_message_id_extra_rows"],
                    "postgres": pq["duplicate_non_null_message_id_extra_rows"],
                },
                "gmail_sent_rows": {"sqlite": sq["gmail_sent_rows"], "postgres": pq["gmail_sent_rows"]},
                "orphan_counts_postgres": orphans,
                "all_passed": val_ok,
            }
            result["ok"] = val_ok
            if not val_ok:
                result["errors"].append("post-load validation failed (see validation details)")
                result["warnings"].append(
                    "archive.* may not match SQLite; consider --replace and re-run the migration."
                )
                pconn.commit()
                sconn.close()
                _write_json(args.json_out, result)
                print(result["errors"][-1], file=sys.stderr)
                return 1

        pconn.commit()
    finally:
        pconn.close()

    sconn.close()
    _write_json(args.json_out, result)
    print("migration completed:", json.dumps(result["loaded"], indent=2))
    return 0 if result["ok"] else 1


def _write_json(path: Path | None, doc: dict[str, Any]) -> None:
    if path is None:
        return
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
