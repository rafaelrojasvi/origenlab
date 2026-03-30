#!/usr/bin/env python3
"""SQLite → JSONL. Paths from .env / ORIGENLAB_*."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.export_jsonl import export_jsonl, export_jsonl_with_phase2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--phase2",
        action="store_true",
        help="include Phase 2 body fields (full_body_clean, top_reply_clean, etc.)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="override output path (default: ORIGENLAB_JSONL_PATH or phase2 sibling)",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    out_path = args.output
    if out_path is None:
        out_path = settings.resolved_jsonl_path()
        if args.phase2:
            out_path = out_path.with_name(out_path.stem + "_phase2.jsonl")

    if not db_path.is_file():
        print(f"SQLite DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if args.phase2:
        n = export_jsonl_with_phase2(db_path, out_path)
    else:
        n = export_jsonl(db_path, out_path)
    print(f"Wrote {n} lines to {out_path}")


if __name__ == "__main__":
    main()
