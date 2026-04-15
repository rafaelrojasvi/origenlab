#!/usr/bin/env python3
"""Preflight trust check: DB, Sent history, sidecars, mart, optional commercial layer (read-only)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)
from origenlab_email_pipeline.outbound_readiness_check import (
    assess_outbound_readiness,
    print_human_report,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: resolved from settings / ORIGENLAB_SQLITE_PATH)",
    )
    p.add_argument(
        "--gmail-user",
        default=None,
        help="Workspace Gmail for Sent checks (default: ORIGENLAB_GMAIL_WORKSPACE_USER or contacto@origenlab.cl).",
    )
    p.add_argument(
        "--sent-folder",
        action="append",
        dest="sent_folders",
        default=None,
        help=(
            "Sent folder label (repeatable). "
            "Default: same shared pair as canonical outbound CLIs (see outbound_core.DEFAULT_SENT_FOLDERS)."
        ),
    )
    p.add_argument(
        "--max-staleness-days",
        type=float,
        default=14.0,
        help="Warn if mart / Sent newest timestamps are older than this many days (default: 14)",
    )
    p.add_argument(
        "--strict-commercial-required",
        action="store_true",
        help="Fail if commercial precheck tables/view are missing (opportunity_candidate + queue view)",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full structured report JSON to this path",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    path = (args.db or settings.resolved_sqlite_path()).resolve()
    exists = path.is_file()

    if not exists:
        report = assess_outbound_readiness(
            sqlite3.connect(":memory:"),
            sqlite_path=path,
            sqlite_exists=False,
            gmail_user=gmail_user,
            sent_folders=resolve_outbound_sent_folders(args.sent_folders),
            max_staleness_days=args.max_staleness_days,
            strict_commercial_required=args.strict_commercial_required,
        )
        print_human_report(report)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(report.to_json_obj(), indent=2), encoding="utf-8")
        return 1

    if args.sent_folders is not None:
        folders = tuple(f.strip() for f in args.sent_folders if f.strip())
        if not folders:
            print("No non-empty --sent-folder values provided.", file=sys.stderr)
            return 2
    else:
        folders = resolve_outbound_sent_folders(None)

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        report = assess_outbound_readiness(
            conn,
            sqlite_path=path,
            sqlite_exists=True,
            gmail_user=gmail_user,
            sent_folders=folders,
            max_staleness_days=args.max_staleness_days,
            strict_commercial_required=args.strict_commercial_required,
        )
    finally:
        conn.close()

    print_human_report(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report.to_json_obj(), indent=2), encoding="utf-8")

    return 1 if report.verdict == "not_ready" else 0


if __name__ == "__main__":
    raise SystemExit(main())
