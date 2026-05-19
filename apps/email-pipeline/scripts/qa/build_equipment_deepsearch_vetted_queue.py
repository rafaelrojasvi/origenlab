#!/usr/bin/env python3
"""Gate deep-search opportunities through equipment-first + DNR/Sent checks (reports only).

Read-only on SQLite and Gmail. Does not send email or mutate databases.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.equipment_deepsearch_vetted_queue import build_vetted_queue

_ACTIVE_CURRENT = _REPO / "reports/out/active/current"
_ACTIVE_ROOT = _REPO / "reports/out/active"
_DEFAULT_DB = Path("/home/rafael/data/origenlab-email/sqlite/emails.sqlite")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date-suffix", default="20260518")
    p.add_argument("--reports-dir", type=Path, default=_ACTIVE_CURRENT)
    p.add_argument("--active-root", type=Path, default=_ACTIVE_ROOT)
    p.add_argument("--db", type=Path, default=None, help="SQLite (read-only); default from settings")
    args = p.parse_args()

    suffix = args.date_suffix
    reports = args.reports_dir
    input_path = reports / f"equipment_deep_research_opportunities_{suffix}.csv"
    output_csv = reports / f"equipment_deepsearch_vetted_queue_{suffix}.csv"
    output_md = reports / f"equipment_deepsearch_vetted_queue_{suffix}.md"
    operator_queue = reports / f"equipment_first_operator_queue_{suffix}.csv"

    settings = load_settings()
    db_path = (args.db or settings.resolved_sqlite_path()).resolve()

    try:
        stats = build_vetted_queue(
            input_path=input_path,
            output_csv=output_csv,
            output_md=output_md,
            operator_queue_path=operator_queue,
            active_current=reports,
            active_root=args.active_root,
            db_path=db_path if db_path.is_file() else None,
            date_suffix=suffix,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"wrote: {output_csv}")
    print(f"wrote: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
