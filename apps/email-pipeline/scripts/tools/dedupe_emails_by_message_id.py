#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): DELETEs duplicate emails rows and cascades attachment cleanup.
# Irreversible without restoring DB from backup. See docs/SCRIPT_MAP.md.
# -----------------------------------------------------------------------------
"""Remove duplicate rows in emails table, keeping one per message_id (exact match).

Enables SQLite foreign key enforcement so ON DELETE CASCADE removes attachment rows
when duplicate emails are deleted. Also runs an explicit orphan cleanup as a
safeguard (e.g. if dedupe was previously run without FK enabled). Idempotent.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings


def main() -> None:
    db_path = load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    # Wait up to 60s for lock (e.g. another report or IDE has DB open)
    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.execute("PRAGMA foreign_keys=ON")

    before_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    before_att = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]

    # 1) Explicit orphan cleanup: remove attachment rows whose email_id no longer exists
    #    (safeguard for DBs that were deduped before FK was enabled)
    conn.execute(
        "DELETE FROM attachments WHERE email_id NOT IN (SELECT id FROM emails)"
    )
    conn.commit()
    after_orphan_cleanup = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    orphans_removed = before_att - after_orphan_cleanup

    # 2) Keep one row per message_id; CASCADE deletes their attachments
    conn.execute(
        """
        DELETE FROM emails
        WHERE id NOT IN (
            SELECT MIN(id) FROM emails
            GROUP BY COALESCE(message_id, id)
        )
        """
    )
    conn.commit()
    after_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    after_att = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    orphan_count = conn.execute(
        "SELECT COUNT(*) FROM attachments WHERE email_id NOT IN (SELECT id FROM emails)"
    ).fetchone()[0]
    conn.close()

    removed_dupes = before_emails - after_emails
    print(
        f"Before: {before_emails:,} emails, {before_att:,} attachments | "
        f"After: {after_emails:,} emails, {after_att:,} attachments"
    )
    print(f"Removed: {removed_dupes:,} duplicate emails | Orphan attachments removed: {orphans_removed:,}")
    print(f"Orphan attachment rows (post-dedupe): {orphan_count:,}")


if __name__ == "__main__":
    main()
