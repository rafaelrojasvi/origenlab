#!/usr/bin/env python3
"""Build post-send digest reports after manual outreach (read-only Gmail analysis)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.campaigns.post_send_digest import build_post_send_digest
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
    )
    ap.add_argument("--since-days", type=int, default=2)
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument(
        "--ingest-stats-json",
        default="",
        help='Optional JSON object string with ingest row counts, e.g. {"inbox":1,"sent":2}',
    )
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    ingest_stats = json.loads(args.ingest_stats_json) if args.ingest_stats_json.strip() else None

    conn = connect(db_path)
    try:
        summary = build_post_send_digest(
            conn,
            args.out_dir,
            since_days=args.since_days,
            sent_folders=resolve_outbound_sent_folders(args.sent_folder),
            gmail_user=resolve_outbound_gmail_user(settings, explicit=args.gmail_user),
            ingest_stats=ingest_stats,
        )
    finally:
        conn.close()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
