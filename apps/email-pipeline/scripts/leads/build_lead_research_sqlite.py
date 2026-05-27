#!/usr/bin/env python3
"""Build SQLite lead_research_* from Phase 10B review/blocked CSV outputs."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.lead_research.lead_research_builder import (  # noqa: E402
    build_lead_research_sqlite,
    default_phase10b_paths,
)


def _default_sqlite_db() -> Path:
    env = os.environ.get("ORIGENLAB_SQLITE_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "data" / "origenlab-email" / "sqlite" / "emails.sqlite"


def main(argv: list[str] | None = None) -> int:
    repo_root = _ROOT.parents[1]
    default_review, default_blocked, default_followup = default_phase10b_paths(repo_root)

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None)
    p.add_argument("--review-csv", type=Path, default=default_review)
    p.add_argument("--blocked-csv", type=Path, default=default_blocked)
    p.add_argument("--followup-csv", type=Path, default=default_followup)
    p.add_argument("--batch-key", default="phase10b_current")
    p.add_argument("--source-name", default="deepsearch_phase10b")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    review = args.review_csv.expanduser().resolve()
    blocked = args.blocked_csv.expanduser().resolve()
    if not review.is_file():
        print(f"ERROR: review CSV not found: {review}", file=sys.stderr)
        return 2

    sqlite_path = (args.sqlite_db or _default_sqlite_db()).expanduser().resolve()
    followup = args.followup_csv.expanduser().resolve() if args.followup_csv else None

    if args.dry_run:
        conn = sqlite3.connect(":memory:")
    else:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(sqlite_path)

    try:
        summary = build_lead_research_sqlite(
            conn,
            review_csv=review,
            blocked_csv=blocked,
            followup_csv=followup if followup and followup.is_file() else None,
            batch_key=args.batch_key,
            source_name=args.source_name,
            dry_run=args.dry_run,
        )
    finally:
        conn.close()

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
