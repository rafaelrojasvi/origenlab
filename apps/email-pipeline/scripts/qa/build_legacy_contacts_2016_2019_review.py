#!/usr/bin/env python3
"""Build read-only review CSVs from legacy 2016–2019 contact workbook (no sends)."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.lead_research.legacy_contacts_2016_2019 import (
    build_legacy_contacts_review,
    merge_legacy_possible_buyers_to_lead_research,
    read_legacy_workbook_xls,
    stage_legacy_contacts_to_sqlite,
    write_legacy_review_outputs,
)
from origenlab_email_pipeline.leads.contacted_universe_audit import connect_readonly
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)

DEFAULT_XLS = Path.home() / "data/origenlab-local-assets/legacy-contacts/Base de datos 2016-2019.xls"
DEFAULT_OUT = _ROOT / "reports" / "out" / "active" / "current"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--xls-path",
        type=Path,
        default=DEFAULT_XLS,
        help="Path to legacy .xls workbook",
    )
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--exclusion-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="Directory with contacted/bounced/suppression CSVs",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path for safety matching")
    ap.add_argument("--no-db", action="store_true", help="Skip SQLite safety (CSV exclusions only)")
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument(
        "--copy-to",
        type=Path,
        default=None,
        help="Optional copy of raw .xls outside repo (default: skip if --xls-path exists)",
    )
    ap.add_argument(
        "--stage-sqlite",
        action="store_true",
        help="Write legacy_contact_raw / legacy_contact_normalized staging tables",
    )
    ap.add_argument(
        "--merge-prospectos",
        action="store_true",
        help="Insert possible_buyer_review rows into lead_research_prospect (review-only)",
    )
    ap.add_argument("--dry-run-merge", action="store_true")
    args = ap.parse_args(argv)

    xls_path = args.xls_path.expanduser().resolve()
    if not xls_path.is_file():
        print(f"Workbook not found: {xls_path}", file=sys.stderr)
        return 1

    if args.copy_to:
        dest = args.copy_to.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(xls_path, dest)
        print(f"Copied workbook to {dest}")

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn_ro = None
    conn_rw = None
    if not args.no_db and db_path.is_file():
        need_write = args.stage_sqlite or args.merge_prospectos
        if need_write:
            conn_rw = sqlite3.connect(str(db_path))
            conn_ro = conn_rw
        else:
            conn_ro = connect_readonly(db_path)
    elif not args.no_db:
        print(f"SQLite not found (CSV exclusions only): {db_path}", file=sys.stderr)

    gmail_user = ""
    sent_folders: tuple[str, ...] = ()
    if conn_ro is not None:
        gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
        sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    try:
        result = build_legacy_contacts_review(
            xls_path,
            exclusion_dir=args.exclusion_dir.resolve(),
            conn=conn_ro,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
        )
        paths = write_legacy_review_outputs(result, args.out_dir.resolve())

        if args.stage_sqlite and conn_rw is not None:
            raw_rows, _ = read_legacy_workbook_xls(xls_path)
            counts = stage_legacy_contacts_to_sqlite(
                conn_rw, raw_rows, result.normalized_rows, replace=True
            )
            print(f"Staged SQLite: {counts}")

        if args.merge_prospectos and conn_rw is not None:
            merge_stats = merge_legacy_possible_buyers_to_lead_research(
                conn_rw,
                result.normalized_rows,
                dry_run=args.dry_run_merge,
            )
            print(f"Prospectos merge: {merge_stats}")
    finally:
        if conn_ro is not None and conn_ro is not conn_rw:
            conn_ro.close()
        if conn_rw is not None:
            conn_rw.close()

    s = result.summary
    print("Legacy contacts 2016–2019 review (read-only) — NO SEND")
    print(f"  Raw rows:              {s.get('raw_rows')}")
    print(f"  Normalized rows:       {s.get('normalized_rows')}")
    print(f"  Unique valid emails:   {s.get('unique_valid_emails')}")
    print(f"  Possible buyer review: {s.get('possible_buyer_review')}")
    print(f"  Already contacted:     {s.get('already_contacted_exact')}")
    print(f"  Bounced/suppressed:    {s.get('bounced_or_suppressed')}")
    print(f"  Inspection:            {paths['inspection']}")
    print(f"  Summary:               {paths['summary_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
