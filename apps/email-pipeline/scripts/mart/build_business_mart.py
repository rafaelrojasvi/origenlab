#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): Rebuild path deletes mart tables (contact_master, etc.)
# before repopulating. Run only when you intend a full mart refresh.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Build the client-facing business mart tables (reproducible).

This script materializes:
- contact_master
- organization_master
- document_master
- opportunity_signals

Raw archive tables are not modified.

**Source tiers:** the mart scans **all** rows in ``emails`` (mbox/PST legacy plus Workspace Gmail).
Operational views (Streamlit, outbound readiness, case queues) default to **canonical** rows
``gmail:contacto@origenlab.cl/…`` only — see :mod:`origenlab_email_pipeline.contacto_gmail_source`
and ``docs/RUNBOOK.md`` (source of truth).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import infer_internal_domains_from_top_senders
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.build_runner import ensure_fast_indexes, run_business_mart_build
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.freshness_dates import MART_DATE_SLACK_DAYS_DEFAULT
from origenlab_email_pipeline.pipeline_run_recorder import start_run
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal-domain", action="append", default=[], help="repeatable; add internal domains (default: inferred)")
    ap.add_argument("--limit-emails", type=int, default=None, help="debug: limit emails scanned")
    ap.add_argument("--rebuild", action="store_true", help="truncate and rebuild mart tables")
    ap.add_argument(
        "--dashboard-fast",
        action="store_true",
        help="Fast daily mode (canonical/recent rows, skip heavy stages when safe).",
    )
    ap.add_argument(
        "--canonical-only",
        action="store_true",
        help="Process only canonical contacto Gmail source rows.",
    )
    ap.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Restrict email scan to date_iso within N days (best effort).",
    )
    ap.add_argument(
        "--skip-document-master-if-unchanged",
        action="store_true",
        help="Skip rebuilding document_master when attachment/extract signature is unchanged.",
    )
    ap.add_argument(
        "--mart-date-slack-days",
        type=int,
        default=MART_DATE_SLACK_DAYS_DEFAULT,
        help=(
            "Exclude email date_iso from mart first/last_seen (and document sent_at) when "
            "parsed calendar date is more than this many days after local today (default: "
            f"{MART_DATE_SLACK_DAYS_DEFAULT}). Raw emails table is never modified."
        ),
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    conn = connect(db_path)
    migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART})
    ensure_fast_indexes(conn)

    run_id = start_run(
        conn,
        script_name="scripts/mart/build_business_mart.py",
        notes="business mart build",
    )

    internal_domains = {d.lower().strip() for d in (args.internal_domain or []) if d.strip()}
    if not internal_domains:
        internal_domains = infer_internal_domains_from_top_senders(conn, max_n=3, sender_limit=50)

    print(f"DB: {db_path}")
    print(f"Internal domains (guess): {sorted(internal_domains)[:10]}")
    if args.dashboard_fast:
        print("[mode] dashboard-fast enabled")
    if args.canonical_only:
        print("[mode] canonical-only enabled")
    if args.since_days is not None:
        print(f"[mode] since-days={args.since_days}")
    mart_slack = int(args.mart_date_slack_days)
    if mart_slack < 0 or mart_slack > 3660:
        mart_slack = MART_DATE_SLACK_DAYS_DEFAULT
    print(f"Mart date slack days (plausible timeline): {mart_slack}")

    if args.rebuild:
        conn.executescript(
            """
            DELETE FROM opportunity_signals;
            DELETE FROM document_master;
            DELETE FROM contact_master;
            DELETE FROM organization_master;
            """
        )
        conn.commit()

    options = MartBuildOptions(
        internal_domains=frozenset(internal_domains),
        limit_emails=args.limit_emails,
        dashboard_fast=bool(args.dashboard_fast),
        canonical_only=bool(args.canonical_only),
        since_days=args.since_days,
        skip_document_master_if_unchanged=bool(args.skip_document_master_if_unchanged),
        mart_date_slack_days=mart_slack,
    )
    built_at = run_business_mart_build(conn, run_id, options)
    conn.close()
    print("Done.")
    print(f"created_at|{built_at}")


if __name__ == "__main__":
    main()
