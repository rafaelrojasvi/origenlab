#!/usr/bin/env python3
"""Backfill Phase 2.2 text fields (full_body_clean, top_reply_clean) for existing rows."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.parse_mbox import extract_full_and_top_reply
from origenlab_email_pipeline.progress import iter_with_progress


def main() -> None:
    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.row_factory = sqlite3.Row

    total = conn.execute(
        """
        SELECT COUNT(*) FROM emails
        WHERE full_body_clean IS NULL OR full_body_clean = ''
        """
    ).fetchone()[0]
    print(f"Backfilling Phase 2.2 text fields on {total:,} rows in {db_path}")

    updated = 0
    rows = conn.execute(
        """
        SELECT id, body_text_raw, body_text_clean
        FROM emails
        WHERE full_body_clean IS NULL OR full_body_clean = ''
        """
    )

    for row in iter_with_progress(rows, total=total, desc="Backfill full/top body", unit="emails"):
        structured = {
            "body_text_raw": row["body_text_raw"] or "",
            "body_text_clean": row["body_text_clean"] or "",
        }
        full_body_clean, top_reply_clean = extract_full_and_top_reply(structured)  # type: ignore[arg-type]
        conn.execute(
            """
            UPDATE emails
            SET full_body_clean = ?, top_reply_clean = ?
            WHERE id = ?
            """,
            (full_body_clean, top_reply_clean, row["id"]),
        )
        updated += 1
        if updated % 10_000 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    print(f"Done. Total updated rows: {updated:,}")


if __name__ == "__main__":
    main()

