#!/usr/bin/env python3
"""Read-only audit: duplicate ``message_id`` within canonical Gmail Workspace ``emails`` rows.

Filters ``lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'``. Does not modify SQLite.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
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


def _canonical_where(alias: str = "e") -> str:
    return sql_predicate_contacto_gmail_source(table_alias=alias, coalesce_null=False)


def run_audit(conn: sqlite3.Connection) -> dict[str, Any]:
    cw = _canonical_where("e")
    total = conn.execute(f"SELECT COUNT(*) FROM emails e WHERE {cw}").fetchone()[0]
    with_mid = conn.execute(
        f"""
        SELECT COUNT(*) FROM emails e
        WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
        """
    ).fetchone()[0]

    dup_groups = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    dup_rows = conn.execute(
        f"""
        SELECT SUM(cnt - 1) FROM (
            SELECT COUNT(*) AS cnt
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    dist: list[tuple[int, int]] = []
    cur = conn.execute(
        f"""
        SELECT c, COUNT(*) AS n FROM (
            SELECT COUNT(*) AS c
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING c > 1
        )
        GROUP BY c ORDER BY c
        """
    )
    for r in cur:
        dist.append((int(r[0]), int(r[1])))

    multi_folder_groups = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT e.folder) > 1
        )
        """
    ).fetchone()[0]

    multi_source_groups = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT e.source_file) > 1
        )
        """
    ).fetchone()[0]

    multi_subject = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT e.subject) > 1
        )
        """
    ).fetchone()[0]

    multi_date = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT e.date_iso) > 1
        )
        """
    ).fetchone()[0]

    multi_body_len = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT length(COALESCE(e.body,''))) > 1
        )
        """
    ).fetchone()[0]

    multi_att = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT lower(trim(e.message_id)) AS mid
            FROM emails e
            WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
            GROUP BY lower(trim(e.message_id))
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT COALESCE(e.attachment_count,-1)) > 1
        )
        """
    ).fetchone()[0]

    folder_dup_rows = conn.execute(
        f"""
        SELECT COALESCE(e.folder,'(null)') AS folder, COUNT(*) AS n
        FROM emails e
        WHERE {cw}
          AND lower(trim(e.message_id)) IN (
            SELECT lower(trim(message_id)) FROM emails e2
            WHERE {_canonical_where('e2')}
              AND e2.message_id IS NOT NULL AND trim(e2.message_id) != ''
            GROUP BY lower(trim(e2.message_id))
            HAVING COUNT(*) > 1
          )
        GROUP BY e.folder
        ORDER BY n DESC
        """
    ).fetchall()

    top_dups = conn.execute(
        f"""
        SELECT lower(trim(e.message_id)) AS mid, COUNT(*) AS c
        FROM emails e
        WHERE {cw} AND e.message_id IS NOT NULL AND trim(e.message_id) != ''
        GROUP BY lower(trim(e.message_id))
        HAVING c > 1
        ORDER BY c DESC, mid
        LIMIT 50
        """
    ).fetchall()

    examples: list[dict[str, Any]] = []
    for r in top_dups[:10]:
        mid = r["mid"]
        rows = conn.execute(
            f"""
            SELECT id, source_file, folder, date_iso, subject,
                   length(COALESCE(body,'')) AS blen,
                   COALESCE(attachment_count,0) AS ac
            FROM emails e
            WHERE {cw} AND lower(trim(e.message_id)) = ?
            ORDER BY e.id
            LIMIT 12
            """,
            (mid,),
        ).fetchall()
        examples.append(
            {
                "message_id": mid,
                "count": int(r["c"]),
                "rows": [dict(x) for x in rows],
            }
        )

    # Attachments on rows that would be deleted if we kept MIN(id) per dup group
    att_dup_only = conn.execute(
        f"""
        SELECT COUNT(*) FROM attachments a
        WHERE a.email_id IN (
            SELECT e.id FROM emails e
            JOIN (
                SELECT lower(trim(message_id)) AS mid, MIN(id) AS keep_id
                FROM emails e2
                WHERE {_canonical_where('e2')}
                  AND e2.message_id IS NOT NULL AND trim(e2.message_id) != ''
                GROUP BY lower(trim(e2.message_id))
                HAVING COUNT(*) > 1
            ) d ON lower(trim(e.message_id)) = d.mid AND e.id != d.keep_id
            WHERE {cw}
        )
        """
    ).fetchone()[0]

    att_total = conn.execute(
        f"""
        SELECT COUNT(*) FROM attachments a
        JOIN emails e ON e.id = a.email_id
        WHERE {cw}
        """
    ).fetchone()[0]

    return {
        "canonical_total_rows": int(total),
        "canonical_rows_with_message_id": int(with_mid),
        "duplicate_message_id_groups": int(dup_groups),
        "duplicate_extra_rows": int(dup_rows or 0),
        "group_size_distribution": [{"group_size": a, "num_message_ids": b} for a, b in dist],
        "duplicate_groups_with_multi_folder": int(multi_folder_groups),
        "duplicate_groups_with_multi_source_file": int(multi_source_groups),
        "duplicate_groups_with_multi_subject": int(multi_subject),
        "duplicate_groups_with_multi_date_iso": int(multi_date),
        "duplicate_groups_with_multi_body_len": int(multi_body_len),
        "duplicate_groups_with_multi_attachment_count": int(multi_att),
        "rows_in_duplicate_groups_by_folder": [
            {"folder": str(x[0]), "row_count": int(x[1])} for x in folder_dup_rows
        ],
        "top_50_duplicate_groups": [{"message_id": str(x[0]), "count": int(x[1])} for x in top_dups],
        "example_duplicate_groups_detail": examples,
        "attachments_on_non_min_id_duplicate_rows": int(att_dup_only),
        "attachments_total_canonical_gmail": int(att_total),
    }


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=settings.resolved_sqlite_path())
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, default=None, help="Write JSON report to this path")
    ap.add_argument(
        "--csv-top",
        type=Path,
        default=None,
        help="Write top duplicate groups to CSV (message_id, count)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    db_path = args.db.resolve()
    print(f"SQLite (read-only): {db_path}", file=sys.stderr)
    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    conn = _connect_ro(db_path)
    try:
        payload = run_audit(conn)
        payload["sqlite_path"] = str(db_path)
    finally:
        conn.close()

    if args.csv_top:
        args.csv_top.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_top.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["message_id", "duplicate_count"])
            for row in payload["top_50_duplicate_groups"]:
                w.writerow([row["message_id"], row["count"]])
        print(f"Wrote CSV: {args.csv_top}", file=sys.stderr)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote JSON: {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("=== Canonical Gmail duplicate message_id audit ===", file=sys.stderr)
    for k, v in payload.items():
        if k in ("top_50_duplicate_groups", "example_duplicate_groups_detail", "group_size_distribution"):
            continue
        print(f"{k}: {v}", file=sys.stderr)
    print("\n--- group_size_distribution (size -> num message_ids) ---", file=sys.stderr)
    for row in payload["group_size_distribution"]:
        print(f"  {row}", file=sys.stderr)
    print("\n--- top 50 duplicate groups ---", file=sys.stderr)
    for row in payload["top_50_duplicate_groups"]:
        print(f"  {row['count']:3d}  {row['message_id'][:100]}", file=sys.stderr)
    print("\n--- sample group detail (first 10 of top) ---", file=sys.stderr)
    for ex in payload["example_duplicate_groups_detail"]:
        print(json.dumps(ex, indent=2, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
