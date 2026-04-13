#!/usr/bin/env python3
"""Compare archive-based vs lead-based outreach top candidates (read-only)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.outreach_queue_compare import compare_archive_vs_lead_outreach


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare archive outreach queue against lead outreach queue")
    ap.add_argument("--out-dir", type=Path, required=True, help="Directory for JSON + CSV outputs")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--gmail-user", type=str, default="")
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--archive-fetch-cap", type=int, default=20000)
    ap.add_argument("--archive-limit", type=int, default=500)
    ap.add_argument("--lead-fetch-cap", type=int, default=4000)
    ap.add_argument("--lead-limit", type=int, default=500)
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS

    conn = connect(db_path)
    try:
        comp = compare_archive_vs_lead_outreach(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            archive_fetch_cap=int(args.archive_fetch_cap),
            archive_limit=int(args.archive_limit),
            lead_fetch_cap=int(args.lead_fetch_cap),
            lead_limit=int(args.lead_limit),
            top_n=int(args.top_n),
        )
    finally:
        conn.close()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = comp.to_dict()
    payload["meta"] = {
        "db_path": str(db_path),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
    }

    (out_dir / "archive_vs_lead_outreach_comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(out_dir / "archive_top20.csv", [x.to_dict() for x in comp.archive_top])
    _write_csv(out_dir / "lead_top20.csv", [x.to_dict() for x in comp.lead_top])
    (out_dir / "overlap_summary.json").write_text(
        json.dumps(comp.overlap_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "archive_blocked_reason_distribution.json").write_text(
        json.dumps(comp.blocked_archive_by_reason, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "archive_top": len(comp.archive_top),
                "lead_top": len(comp.lead_top),
                "overlap_summary": comp.overlap_summary,
                "blocked_archive_by_reason": comp.blocked_archive_by_reason,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
