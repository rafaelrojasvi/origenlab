#!/usr/bin/env python3
"""Validate attachment metadata (Phase 2.3) on the SQLite DB."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.validation.attachment_validation import (
    format_attachment_validation_report,
    run_attachment_validation,
)


def main() -> None:
    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    try:
        result = run_attachment_validation(conn)
    finally:
        conn.close()

    print(format_attachment_validation_report(result, db_path))


if __name__ == "__main__":
    main()
