#!/usr/bin/env python3
"""Read-only OrigenLab email conversation intelligence export."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.qa.conversation_intelligence import (
    build_conversation_intelligence_export,
    print_conversation_intelligence_summary,
    write_conversation_intelligence_outputs,
)


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(settings.resolved_sqlite_path()))
    ap.add_argument("--gmail-user", default=settings.gmail_workspace_user or "contacto@origenlab.cl")
    ap.add_argument(
        "--out-dir",
        default=str(_ROOT / "reports" / "out" / "active" / "current" / "email_conversation_intelligence"),
    )
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--include-noise", action="store_true")
    ap.add_argument(
        "--include-legacy-email-sources",
        action="store_true",
        help=(
            "include all mbox/PST rows in `emails` (may mix contacto@labdelivery exports). "
            "Default: restrict to canonical Workspace Gmail `gmail:contacto@origenlab.cl/` rows only."
        ),
    )
    ap.add_argument("--json-out", default=None)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.is_file():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        result = build_conversation_intelligence_export(
            conn,
            db_path=db_path,
            gmail_user=args.gmail_user,
            since_days=args.since_days,
            include_legacy_email_sources=args.include_legacy_email_sources,
            include_noise=args.include_noise,
        )
    finally:
        conn.close()

    write_conversation_intelligence_outputs(out_dir, result)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result.summary_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print_conversation_intelligence_summary(result.summary_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
