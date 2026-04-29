#!/usr/bin/env python3
"""Export normalized contacted-all emails from Sent + blocking outreach state.

Read-only over SQLite. Writes a deterministic CSV for auxiliary overlap context:
``reports/out/active/outreach_contacted_all.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.marketing_export_context import (
    load_outreach_contacted_norms,
    load_sent_recipient_norms,
)
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "outreach_contacted_all.csv",
        help="Output CSV path (default: reports/out/active/outreach_contacted_all.csv).",
    )
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    conn = _connect_readonly(db_path)
    try:
        sent = load_sent_recipient_norms(conn, gmail_user=gmail_user, sent_folders=sent_folders)
        blocking_state = set(load_outreach_contacted_norms(conn))
    finally:
        conn.close()

    union = sorted(set(sent) | blocking_state)
    duplicates_removed = (len(sent) + len(blocking_state)) - len(union)

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["contact_email"], lineterminator="\n")
        w.writeheader()
        for email in union:
            w.writerow({"contact_email": email})

    payload = {
        "output_path": str(out),
        "sent_unique_count": len(sent),
        "outreach_state_blocking_count": len(blocking_state),
        "union_unique_count": len(union),
        "duplicates_removed": duplicates_removed,
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
