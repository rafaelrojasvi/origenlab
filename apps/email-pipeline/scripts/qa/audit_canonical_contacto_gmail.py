#!/usr/bin/env python3
"""Read-only audit: canonical Gmail Workspace vs legacy labdelivery vs other ``emails`` rows.

Does not modify SQLite. Optional ``--out`` writes JSON to a path you choose.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source


def _connect_ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=120.0)
    conn.row_factory = sqlite3.Row
    return conn


def _top_counts(conn: sqlite3.Connection, where_extra: str, *, limit: int = 12) -> list[dict[str, Any]]:
    cur = conn.execute(
        f"""
        SELECT source_file, COUNT(*) AS n
        FROM emails
        WHERE {where_extra}
        GROUP BY source_file
        ORDER BY n DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [{"source_file": r["source_file"], "n": int(r["n"])} for r in cur]


def _top_folders(conn: sqlite3.Connection, where_extra: str, *, limit: int = 12) -> list[dict[str, Any]]:
    cur = conn.execute(
        f"""
        SELECT COALESCE(folder, '') AS folder, COUNT(*) AS n
        FROM emails
        WHERE {where_extra}
        GROUP BY folder
        ORDER BY n DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [{"folder": r["folder"] or "(null)", "n": int(r["n"])} for r in cur]


def _group_metrics(conn: sqlite3.Connection, *, label: str, where_extra: str) -> dict[str, Any]:
    n = int(conn.execute(f"SELECT COUNT(*) FROM emails WHERE {where_extra}").fetchone()[0])
    row_min = conn.execute(f"SELECT MIN(date_iso) FROM emails WHERE {where_extra}").fetchone()
    row_max = conn.execute(f"SELECT MAX(date_iso) FROM emails WHERE {where_extra}").fetchone()
    miss_mid = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (message_id IS NULL OR trim(message_id) = '')
            """
        ).fetchone()[0]
    )
    miss_date = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (date_iso IS NULL OR trim(date_iso) = '')
            """
        ).fetchone()[0]
    )
    empty_body = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (body IS NULL OR trim(body) = '')
            """
        ).fetchone()[0]
    )
    empty_full = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (full_body_clean IS NULL OR trim(full_body_clean) = '')
            """
        ).fetchone()[0]
    )
    empty_top = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (top_reply_clean IS NULL OR trim(top_reply_clean) = '')
            """
        ).fetchone()[0]
    )
    future_susp = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND date_iso IS NOT NULL AND trim(date_iso) != ''
              AND date(date_iso) > date('now', '+2 days')
            """
        ).fetchone()[0]
    )
    before_2010 = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND date_iso IS NOT NULL AND length(date_iso) >= 4
              AND substr(date_iso, 1, 4) < '2010'
            """
        ).fetchone()[0]
    )
    sent_like = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (
                lower(COALESCE(folder, '')) LIKE '%enviados%'
                OR lower(COALESCE(folder, '')) LIKE '%sent mail%'
              )
            """
        ).fetchone()[0]
    )
    inbox_like = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM emails
            WHERE {where_extra}
              AND (
                lower(COALESCE(folder, '')) LIKE '%inbox%'
                OR lower(COALESCE(folder, '')) LIKE '%bandeja de entrada%'
              )
            """
        ).fetchone()[0]
    )
    dup_extra = f"{where_extra} AND message_id IS NOT NULL AND trim(message_id) != ''"
    dup_groups = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT message_id FROM emails WHERE {dup_extra}
                GROUP BY message_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )
    dup_rows_raw = conn.execute(
        f"""
        SELECT COALESCE(SUM(cnt - 1), 0) FROM (
            SELECT COUNT(*) AS cnt FROM emails WHERE {dup_extra}
            GROUP BY message_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    dup_rows = int(dup_rows_raw or 0)
    att_n = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM attachments
            WHERE email_id IN (SELECT id FROM emails WHERE {where_extra})
            """
        ).fetchone()[0]
    )

    return {
        "label": label,
        "row_count": n,
        "min_date_iso": row_min[0] if row_min else None,
        "max_date_iso": row_max[0] if row_max else None,
        "missing_message_id": miss_mid,
        "missing_date_iso": miss_date,
        "empty_body": empty_body,
        "empty_full_body_clean": empty_full,
        "empty_top_reply_clean": empty_top,
        "sent_folder_like_count": sent_like,
        "inbox_like_count": inbox_like,
        "suspicious_future_after_today_plus_2d": future_susp,
        "rows_date_iso_year_before_2010": before_2010,
        "duplicate_message_id_groups": dup_groups,
        "duplicate_message_id_extra_rows": dup_rows,
        "attachments_linked": att_n,
        "source_file_top": _top_counts(conn, where_extra),
        "folder_top": _top_folders(conn, where_extra),
    }


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=settings.resolved_sqlite_path(), help="SQLite path (read-only)")
    ap.add_argument("--json", action="store_true", help="print one JSON object to stdout")
    ap.add_argument("--out", type=Path, default=None, help="write JSON report to this path")
    args = ap.parse_args(list(argv) if argv is not None else None)

    db_path: Path = args.db.resolve()
    print(f"SQLite (read-only): {db_path}", file=sys.stderr)
    if not db_path.is_file():
        print(f"ERROR: database file not found: {db_path}", file=sys.stderr)
        return 2

    pred_canon = sql_predicate_contacto_gmail_source()
    where_canon = pred_canon
    where_legacy = "lower(source_file) LIKE '%contacto@labdelivery%'"
    where_other = f"NOT ({where_canon}) AND NOT ({where_legacy})"

    conn = _connect_ro(db_path)
    try:
        payload: dict[str, Any] = {
            "sqlite_path": str(db_path),
            "canonical_predicate": pred_canon,
            "groups": {
                "A_canonical_gmail_contacto": _group_metrics(conn, label="canonical_gmail", where_extra=where_canon),
                "B_legacy_labdelivery": _group_metrics(conn, label="legacy_labdelivery", where_extra=where_legacy),
                "C_other": _group_metrics(conn, label="other", where_extra=where_other),
            },
        }
    finally:
        conn.close()

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote JSON report: {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    for key, block in payload["groups"].items():
        print(f"\n=== {key} ===", file=sys.stderr)
        for k, v in block.items():
            if k in ("source_file_top", "folder_top"):
                print(f"{k}:", file=sys.stderr)
                for row in v:
                    print(f"  {row}", file=sys.stderr)
            else:
                print(f"{k}: {v}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
