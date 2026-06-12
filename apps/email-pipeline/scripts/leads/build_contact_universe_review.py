#!/usr/bin/env python3
"""Read-only contact universe review export (no Gmail/SQLite/Postgres mutations)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.leads.contact_universe_review import (
    build_contact_universe_review,
    default_out_dir,
    write_contact_universe_review_outputs,
)
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None, help="SQLite path (read-only)")
    p.add_argument(
        "--active-current",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
        help="Active current reports directory for input CSVs",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: <active-current>/contact_universe_review)",
    )
    p.add_argument(
        "--do-not-repeat-csv",
        type=Path,
        default=None,
        help="Optional do_not_repeat_master.csv override",
    )
    p.add_argument("--gmail-user", default=None)
    p.add_argument("--sent-folder", action="append", default=[])
    p.add_argument(
        "--focus-domain",
        action="append",
        default=[],
        help="Optional domain filter (repeatable)",
    )
    p.add_argument(
        "--limit-sources",
        type=int,
        default=None,
        help="Cap number of source files scanned (debug/smoke)",
    )
    p.add_argument(
        "--include-inventory-sources",
        action="store_true",
        help="Also scan contact_csv_inventory.json paths (default: inventory metadata only)",
    )
    p.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    active_current = args.active_current.resolve()
    out_dir = (args.out_dir or default_out_dir(active_current)).resolve()
    dnr_csv = args.do_not_repeat_csv or (active_current / "do_not_repeat_master.csv")
    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)
    focus = frozenset(d.strip().lower() for d in args.focus_domain if d.strip()) or None

    result = build_contact_universe_review(
        repo_root=_ROOT,
        sqlite_path=db_path,
        active_current=active_current,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        focus_domains=focus,
        limit_sources=args.limit_sources,
        include_inventory_sources=args.include_inventory_sources,
        do_not_repeat_csv=dnr_csv if dnr_csv.is_file() else None,
    )
    paths = write_contact_universe_review_outputs(result, out_dir)
    summary = {**result.summary, "out_dir": str(out_dir)}

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print("Contact universe review (read-only)")
        print(f"  out_dir={out_dir}")
        print(f"  total_candidates={summary['total_candidates']}")
        print(f"  followup_candidates={summary['followup_candidates']}")
        print(f"  net_new_candidates={summary['net_new_candidates']}")
        print(f"  blocked_or_suppressed={summary['blocked_or_suppressed']}")
        for label, path in paths.items():
            print(f"  wrote {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
