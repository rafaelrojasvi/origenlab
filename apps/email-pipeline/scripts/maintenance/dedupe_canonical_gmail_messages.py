#!/usr/bin/env python3
"""Remove duplicate canonical Gmail ``emails`` rows (same ``message_id``, same Workspace ingest).

**Default: dry-run** (no writes). Pass ``--apply`` plus ``--ack-sqlite-backup`` to execute ``DELETE``.

Only touches rows where ``lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'``. Never deletes
legacy mbox paths.

**Before --apply:** take a filesystem backup of the SQLite file. ``document_master`` / mart rows
that reference deleted ``emails.id`` may cascade; plan ``build_business_mart --rebuild`` if needed.

See also: ``scripts/qa/audit_canonical_gmail_duplicates.py``.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.canonical_gmail_dedupe import (
    EmailRowForDedupe,
    canonical_gmail_where_sql,
    delete_ids_for_groups,
    group_rows_by_normalized_mid,
)
from origenlab_email_pipeline.config import load_settings

_CHUNK = 400


def format_cp_sqlite_backup_command(db_path: Path, *, ts_utc: str) -> str:
    """Shell ``cp`` suggestion with **quoted** paths so src and dest never run together."""
    src = db_path.expanduser().resolve()
    dest = src.parent / f"{src.name}.backup-{ts_utc}"
    return f"cp {shlex.quote(str(src))} {shlex.quote(str(dest))}"


def _chunks(ids: list[int], n: int) -> list[list[int]]:
    return [ids[i : i + n] for i in range(0, len(ids), n)]


def _load_duplicate_cluster_rows(conn: sqlite3.Connection) -> list[EmailRowForDedupe]:
    cw = canonical_gmail_where_sql("e")
    cur = conn.execute(
        f"""
        SELECT e.id, e.message_id, e.folder, e.source_file,
               COALESCE(e.attachment_count, 0),
               length(COALESCE(e.body, '')),
               length(COALESCE(e.full_body_clean, '')),
               length(COALESCE(e.top_reply_clean, '')),
               length(COALESCE(e.body_text_clean, ''))
        FROM emails e
        WHERE {cw}
          AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
          AND lower(trim(e.message_id)) IN (
            SELECT lower(trim(e2.message_id))
            FROM emails e2
            WHERE {canonical_gmail_where_sql('e2')}
              AND e2.message_id IS NOT NULL AND trim(e2.message_id) != ''
            GROUP BY lower(trim(e2.message_id))
            HAVING COUNT(*) > 1
          )
        """
    )
    return [
        EmailRowForDedupe(
            id=int(r[0]),
            message_id=str(r[1]),
            folder=r[2],
            source_file=r[3],
            attachment_count=int(r[4]),
            body_len=int(r[5]),
            full_body_len=int(r[6]),
            top_reply_len=int(r[7]),
            body_text_clean_len=int(r[8]),
        )
        for r in cur.fetchall()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=settings.resolved_sqlite_path())
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually DELETE duplicate rows (requires --ack-sqlite-backup)",
    )
    ap.add_argument(
        "--ack-sqlite-backup",
        action="store_true",
        help="confirm you have a filesystem backup of the SQLite file",
    )
    ap.add_argument(
        "--log-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "maintenance",
        help="directory for JSONL delete logs",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    db_path = args.db.expanduser().resolve()
    print(f"SQLite: {db_path}", file=sys.stderr)
    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_cmd = format_cp_sqlite_backup_command(db_path, ts_utc=ts)
    print(f"Suggested backup: {backup_cmd}", file=sys.stderr)

    if args.apply and not args.ack_sqlite_backup:
        print("ERROR: --apply requires --ack-sqlite-backup (filesystem backup).", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path), timeout=120.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = _load_duplicate_cluster_rows(conn)
        groups = group_rows_by_normalized_mid(rows)
        dup_groups = {k: v for k, v in groups.items() if len(v) >= 2}
        to_delete = delete_ids_for_groups(dup_groups)

        print(f"Duplicate groups: {len(dup_groups)}", file=sys.stderr)
        print(f"Rows to delete: {len(to_delete)}", file=sys.stderr)
        if not to_delete:
            print("Nothing to do (no duplicate message_id groups).", file=sys.stderr)
            return 0
        if len(to_delete) <= 30:
            print(f"Delete ids: {to_delete}", file=sys.stderr)
        else:
            print(f"Delete ids (first 30): {to_delete[:30]} …", file=sys.stderr)

        if not args.apply:
            print("Dry-run only (no DELETE). Pass --apply --ack-sqlite-backup after backup.", file=sys.stderr)
            return 0

        args.log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = args.log_dir / f"dedupe_canonical_gmail_{ts}.jsonl"
        meta = {
            "event": "dedupe_canonical_gmail_delete",
            "ts_utc": ts,
            "sqlite_path": str(db_path),
            "deleted_row_count": len(to_delete),
        }
        with log_path.open("w", encoding="utf-8") as logf:
            logf.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for chunk in _chunks(to_delete, _CHUNK):
                ph = ",".join("?" * len(chunk))
                cur2 = conn.execute(
                    f"""
                    SELECT e.id, e.message_id, e.folder, e.source_file
                    FROM emails e
                    WHERE e.id IN ({ph})
                    """,
                    chunk,
                )
                for r in cur2.fetchall():
                    logf.write(
                        json.dumps(
                            {
                                "deleted_email_id": int(r[0]),
                                "message_id": r[1],
                                "folder": r[2],
                                "source_file": r[3],
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

        conn.execute("PRAGMA foreign_keys=ON")
        for chunk in _chunks(to_delete, _CHUNK):
            ph = ",".join("?" * len(chunk))
            conn.execute(f"DELETE FROM emails WHERE id IN ({ph})", chunk)
        conn.commit()
        print(f"Deleted {len(to_delete)} rows. Log: {log_path}", file=sys.stderr)
        print("Consider: uv run python scripts/mart/build_business_mart.py --rebuild", file=sys.stderr)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
