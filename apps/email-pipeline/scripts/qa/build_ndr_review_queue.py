#!/usr/bin/env python3
"""Build read-only NDR review queues and suggested allowlists (no apply)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from origenlab_email_pipeline.mart_core_postgres_migrate import resolve_sqlite_path
from origenlab_email_pipeline.qa.ndr_review_queue import (
    build_ndr_review_queue,
    default_date_label,
    default_out_dir,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since-days", type=int, default=2)
    p.add_argument("--sqlite-path", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--date-label", default=None, help="Folder suffix YYYY_MM_DD")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--fail-on-review-needed", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    date_label = args.date_label or default_date_label()
    sqlite_path = resolve_sqlite_path(args.sqlite_path)
    out_dir = (args.out_dir or default_out_dir(_REPO, date_label)).resolve()
    result = build_ndr_review_queue(
        sqlite_path=sqlite_path,
        out_dir=out_dir,
        since_days=args.since_days,
        date_label=date_label,
    )

    payload = result.summary_json()
    payload["out_dir"] = str(out_dir)
    if args.json_only:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"out_dir={out_dir}")
        print(f"candidates_total={payload['candidates_total']}")
        print(
            "batch_counts="
            + ",".join(f"{k}:{v}" for k, v in payload["batch_counts"].items())
        )
        print(
            "allowlists="
            f"A:{payload['allowlist_batch_a_count']},"
            f"B:{payload['allowlist_batch_b_count']}"
        )

    if args.fail_on_review_needed and payload["candidates_unsuppressed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
