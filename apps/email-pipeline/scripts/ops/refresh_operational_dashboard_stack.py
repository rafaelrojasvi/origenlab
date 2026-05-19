#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# EXPERIMENTAL_PARKED / DASHBOARD_ONLY: Optional dashboard stack (mart + Postgres mirror).
# Not CORE_DAILY. Gmail ingest is off by default. Do not run without explicit approval.
# See docs/EXPERIMENTAL_PARKED.md and docs/RUNBOOK.md (dashboard refresh chain).
# -----------------------------------------------------------------------------
"""Operator wrapper: refresh SQLite mart + Postgres dashboard mirror (no email send).

Gmail ingest mutates SQLite and is **off by default**. Use explicit flags to run ingest steps.
The React dashboard and FastAPI never trigger ingest automatically.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], *, dry_run: bool) -> int:
    print("$", " ".join(cmd))
    if dry_run:
        return 0
    return subprocess.call(cmd, cwd=str(_REPO))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print steps only; do not execute")
    p.add_argument(
        "--run-gmail-inbox",
        action="store_true",
        help="Run Gmail INBOX ingest (mutates SQLite)",
    )
    p.add_argument(
        "--run-gmail-sent",
        action="store_true",
        help="Run Gmail Enviados ingest (mutates SQLite)",
    )
    p.add_argument(
        "--skip-mart",
        action="store_true",
        help="Skip business mart rebuild",
    )
    p.add_argument(
        "--skip-safety",
        action="store_true",
        help="Skip outbound safety memory refresh",
    )
    p.add_argument(
        "--skip-postgres-sync",
        action="store_true",
        help="Skip Postgres dashboard mirror sync",
    )
    p.add_argument(
        "--postgres-sync-dry-run",
        action="store_true",
        help="Pass --dry-run to sync_dashboard_postgres_mirror.py",
    )
    args = p.parse_args(argv)
    py = sys.executable
    rc = 0

    if args.run_gmail_inbox:
        rc |= _run(
            [
                py,
                "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py",
                "--folder",
                "INBOX",
                "--skip-duplicate-message-id",
            ],
            dry_run=args.dry_run,
        )
    if args.run_gmail_sent:
        rc |= _run(
            [
                py,
                "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py",
                "--folder",
                "[Gmail]/Enviados",
                "--skip-duplicate-message-id",
            ],
            dry_run=args.dry_run,
        )

    if not args.skip_mart:
        rc |= _run([py, "scripts/mart/build_business_mart.py", "--rebuild"], dry_run=args.dry_run)

    if not args.skip_safety:
        rc |= _run([py, "scripts/qa/refresh_outbound_safety_memory.py"], dry_run=args.dry_run)

    if not args.skip_postgres_sync:
        sync_cmd = [py, "scripts/sync/sync_dashboard_postgres_mirror.py"]
        if args.postgres_sync_dry_run:
            sync_cmd.append("--dry-run")
        rc |= _run(sync_cmd, dry_run=args.dry_run)

    if not args.run_gmail_inbox and not args.run_gmail_sent:
        print(
            "[info] Gmail ingest skipped (default). New mail requires --run-gmail-inbox "
            "and/or --run-gmail-sent.",
            file=sys.stderr,
        )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
