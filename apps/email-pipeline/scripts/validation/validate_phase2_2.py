#!/usr/bin/env python3
"""Validate Phase 2.2 fields (full_body_clean, top_reply_clean) on the real DB."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings


def main() -> None:
    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== Phase 2.2 validation ===", flush=True)
    print("DB:", db_path, "\n", flush=True)

    total = cur.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    print("Total rows:", f"{total:,}", flush=True)

    non_empty_full = cur.execute(
        "SELECT COUNT(*) FROM emails WHERE full_body_clean IS NOT NULL AND TRIM(full_body_clean) != ''"
    ).fetchone()[0]
    non_empty_top = cur.execute(
        "SELECT COUNT(*) FROM emails WHERE top_reply_clean IS NOT NULL AND TRIM(top_reply_clean) != ''"
    ).fetchone()[0]
    print("\n--- Non-empty fields ---", flush=True)
    print(f"  full_body_clean   non-empty: {non_empty_full:,}", flush=True)
    print(f"  top_reply_clean   non-empty: {non_empty_top:,}", flush=True)

    diff = cur.execute(
        """
        SELECT COUNT(*) FROM emails
        WHERE TRIM(full_body_clean) != '' AND TRIM(top_reply_clean) != ''
          AND TRIM(top_reply_clean) != TRIM(full_body_clean)
        """
    ).fetchone()[0]
    shorter = cur.execute(
        """
        SELECT COUNT(*) FROM emails
        WHERE TRIM(top_reply_clean) != ''
          AND LENGTH(TRIM(top_reply_clean)) < LENGTH(TRIM(full_body_clean))
        """
    ).fetchone()[0]
    empty_top_nonempty_full = cur.execute(
        """
        SELECT COUNT(*) FROM emails
        WHERE TRIM(full_body_clean) != ''
          AND (top_reply_clean IS NULL OR TRIM(top_reply_clean) = '')
        """
    ).fetchone()[0]

    print("\n--- Relationship full vs top ---", flush=True)
    print(f"  top_reply != full_body: {diff:,}", flush=True)
    print(f"  top_reply shorter than full_body: {shorter:,}", flush=True)
    print(f"  top_reply empty but full non-empty: {empty_top_nonempty_full:,}", flush=True)

    print("\n--- Sample: top_reply != full_body (10 rows) ---", flush=True)
    for row in cur.execute(
        """
        SELECT id, subject,
               substr(full_body_clean, 1, 160) AS full_sample,
               substr(top_reply_clean, 1, 160) AS top_sample
        FROM emails
        WHERE TRIM(full_body_clean) != '' AND TRIM(top_reply_clean) != ''
          AND TRIM(top_reply_clean) != TRIM(full_body_clean)
        LIMIT 10
        """
    ):
        print(f"  id={row['id']} subject={row['subject']!r}", flush=True)
        print(f"    full_body_clean: {row['full_sample']!r}", flush=True)
        print(f"    top_reply_clean: {row['top_sample']!r}", flush=True)

    print("\n--- Sample: likely signature-stripped (10 rows) ---", flush=True)
    for row in cur.execute(
        """
        SELECT id, subject,
               substr(full_body_clean, 1, 160) AS full_sample,
               substr(top_reply_clean, 1, 160) AS top_sample
        FROM emails
        WHERE full_body_clean LIKE '%Saludos%' AND top_reply_clean NOT LIKE '%Saludos%'
        LIMIT 10
        """
    ):
        print(f"  id={row['id']} subject={row['subject']!r}", flush=True)
        print(f"    full_body_clean: {row['full_sample']!r}", flush=True)
        print(f"    top_reply_clean: {row['top_sample']!r}", flush=True)

    print("\n--- Sample: likely reply-header-stripped (10 rows) ---", flush=True)
    for row in cur.execute(
        """
        SELECT id, subject,
               substr(full_body_clean, 1, 160) AS full_sample,
               substr(top_reply_clean, 1, 160) AS top_sample
        FROM emails
        WHERE (
            full_body_clean LIKE 'On %wrote:%'
            OR full_body_clean LIKE '%Original Message%'
            OR full_body_clean LIKE 'El %escribio:%'
            OR full_body_clean LIKE 'El %escribió:%'
        )
          AND TRIM(top_reply_clean) != TRIM(full_body_clean)
        LIMIT 10
        """
    ):
        print(f"  id={row['id']} subject={row['subject']!r}", flush=True)
        print(f"    full_body_clean: {row['full_sample']!r}", flush=True)
        print(f"    top_reply_clean: {row['top_sample']!r}", flush=True)

    conn.close()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()

