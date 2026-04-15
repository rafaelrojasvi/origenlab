#!/usr/bin/env python3
"""Read-only precheck: archive shortlist × export gate × commercial intel candidates.

Joins each CSV row to ``contact_candidate`` / ``organization_candidate`` / ``opportunity_candidate``
and summarizes ``v_commercial_candidate_queue``. Writes a review CSV with ``keep`` / ``review`` / ``drop``.

Does not modify SQLite or the export gate. Run after building a shortlist, before
``run_tatiana_pilot_batch.py``.

Example::

  uv run python scripts/leads/precheck_archive_shortlist_commercial.py \\
    --input reports/out/active/archive_outreach_manual_shortlist_11_next3.csv \\
    --out reports/out/active/archive_outreach_manual_shortlist_11_next3_precheck.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.archive_shortlist_commercial_precheck import run_precheck_csv
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_SENT_FOLDERS,
    build_marketing_export_gate_context,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Precheck archive shortlist against export gate + commercial intel (read-only).",
    )
    ap.add_argument("--input", "-i", type=Path, required=True, help="Shortlist CSV from archive export")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output review CSV")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--gmail-user", type=str, default="", help="Mailbox for Sent-history gate")
    ap.add_argument("--sent-folder", action="append", default=[], help="Repeatable sent folders")
    ap.add_argument("--exclude-domain", action="append", default=[], help="Repeatable blocked domain")
    ap.add_argument(
        "--json-summary",
        type=Path,
        default=None,
        help="Optional JSON summary (keep/review/drop counts)",
    )
    args = ap.parse_args()

    if not args.input.is_file():
        print("Input not found:", args.input, file=sys.stderr)
        return 1

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS
    extra_domains = tuple(args.exclude_domain) if args.exclude_domain else ()

    conn = connect(db_path)
    try:
        gate_ctx = build_marketing_export_gate_context(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            extra_exclude_domains=extra_domains,
            strict_contact_graph_noise=True,
        )
        summary = run_precheck_csv(
            conn=conn,
            input_path=args.input,
            out_path=args.out,
            gate_ctx=gate_ctx,
        )
    finally:
        conn.close()

    out = {
        "rows": summary.rows,
        "keep": summary.keep,
        "review": summary.review,
        "drop": summary.drop,
        "out_csv": str(args.out),
        "db_path": str(db_path),
        "gmail_user": gmail_user,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.json_summary:
        args.json_summary.parent.mkdir(parents=True, exist_ok=True)
        args.json_summary.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
