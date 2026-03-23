#!/usr/bin/env python3
"""Post-2.1 validation: verify new body extraction fields and dedupe stats."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings


def main() -> None:
    db_path = load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.row_factory = sqlite3.Row

    print("=== Phase 2.1 validation ===", flush=True)
    print("DB:", db_path, "\n", flush=True)

    # 1. Total rows
    total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    print("Total rows:", f"{total:,}", flush=True)

    # 2. Counts by body_source_type
    print("\n--- body_source_type ---", flush=True)
    for row in conn.execute(
        "SELECT body_source_type, COUNT(*) AS cnt FROM emails GROUP BY body_source_type ORDER BY cnt DESC"
    ):
        print(f"  {row[0]!r}: {row[1]:,}", flush=True)

    # 3. Non-empty raw vs clean
    raw_non_empty = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE body_text_raw IS NOT NULL AND TRIM(body_text_raw) != ''"
    ).fetchone()[0]
    clean_non_empty = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE body_text_clean IS NOT NULL AND TRIM(body_text_clean) != ''"
    ).fetchone()[0]
    print("\n--- Non-empty bodies ---", flush=True)
    print(f"  body_text_raw non-empty:  {raw_non_empty:,}", flush=True)
    print(f"  body_text_clean non-empty: {clean_non_empty:,}", flush=True)

    # 4. has_plain / has_html
    print("\n--- body_has_plain / body_has_html ---", flush=True)
    for row in conn.execute(
        """
        SELECT body_has_plain, body_has_html, COUNT(*) AS cnt
        FROM emails GROUP BY body_has_plain, body_has_html ORDER BY cnt DESC
        """
    ):
        print(f"  has_plain={row[0]}, has_html={row[1]}: {row[2]:,}", flush=True)

    # 5. Sample rows: plain, html, mixed
    print("\n--- Sample: body_source_type = plain ---", flush=True)
    for row in conn.execute(
        "SELECT id, body_source_type, LENGTH(body_text_clean) AS len, SUBSTR(body_text_clean, 1, 120) AS sample FROM emails WHERE body_source_type = 'plain' LIMIT 2"
    ):
        print(f"  id={row[0]} len={row[2]} sample={row[3][:100]!r}...", flush=True)

    print("\n--- Sample: body_source_type = html ---", flush=True)
    for row in conn.execute(
        "SELECT id, body_source_type, LENGTH(body_text_clean) AS len, SUBSTR(body_text_clean, 1, 120) AS sample FROM emails WHERE body_source_type = 'html' LIMIT 2"
    ):
        print(f"  id={row[0]} len={row[2]} sample={row[3][:100]!r}...", flush=True)

    print("\n--- Sample: body_source_type = mixed ---", flush=True)
    for row in conn.execute(
        "SELECT id, body_source_type, LENGTH(body_text_clean) AS len, SUBSTR(body_text_clean, 1, 120) AS sample FROM emails WHERE body_source_type = 'mixed' LIMIT 2"
    ):
        print(f"  id={row[0]} len={row[2]} sample={row[3][:100]!r}...", flush=True)

    # 6. Message-ID dedupe stats
    print("\n--- Message-ID dedupe ---", flush=True)
    missing_mid = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE message_id IS NULL OR TRIM(message_id) = ''"
    ).fetchone()[0]
    distinct_keys = conn.execute(
        "SELECT COUNT(*) FROM (SELECT COALESCE(NULLIF(TRIM(message_id), ''), 'id-' || id) AS k FROM emails GROUP BY k)"
    ).fetchone()[0]
    print(f"  Rows with missing/empty Message-ID: {missing_mid:,}", flush=True)
    print(f"  Unique (message_id or id): {distinct_keys:,}", flush=True)
    print(f"  Duplicate rows (would remove): {total - distinct_keys:,}", flush=True)
    if total:
        print(f"  Duplicate rate: {(total - distinct_keys) / total * 100:.1f}%", flush=True)

    # 7. Anomalies: source_type empty but body non-empty?
    anomaly = conn.execute(
        """
        SELECT COUNT(*) FROM emails
        WHERE body_source_type = 'empty' AND (body_text_raw IS NOT NULL AND TRIM(body_text_raw) != '')
        """
    ).fetchone()[0]
    if anomaly:
        print("\n--- Anomaly ---", flush=True)
        print(f"  Rows with source_type=empty but non-empty body_text_raw: {anomaly}", flush=True)

    conn.close()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
