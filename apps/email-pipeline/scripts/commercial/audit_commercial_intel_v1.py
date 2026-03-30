#!/usr/bin/env python3
"""Audit/reconciliation checks for commercial-intel v1 outputs."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="Optional SQLite override path.")
    ap.add_argument("--strict", action="store_true", help="Fail if no positive signals are present.")
    args = ap.parse_args()

    db_path = args.db or load_settings().resolved_sqlite_path()
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        total_emails = conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"]
        fact_rows = conn.execute("SELECT COUNT(*) c FROM commercial_email_signal_fact").fetchone()["c"]
        considered_emails = conn.execute(
            "SELECT COUNT(DISTINCT email_id) c FROM commercial_email_signal_fact"
        ).fetchone()["c"]
        org_rollups = conn.execute("SELECT COUNT(*) c FROM commercial_org_signal_rollup").fetchone()["c"]
        contact_rollups = conn.execute("SELECT COUNT(*) c FROM commercial_contact_signal_rollup").fetchone()["c"]
        opportunity_facts = conn.execute("SELECT COUNT(*) c FROM commercial_opportunity_fact").fetchone()["c"]
        org_candidates = conn.execute("SELECT COUNT(*) c FROM organization_candidate").fetchone()["c"]
        contact_candidates = conn.execute("SELECT COUNT(*) c FROM contact_candidate").fetchone()["c"]
        opportunity_candidates = conn.execute("SELECT COUNT(*) c FROM opportunity_candidate").fetchone()["c"]

        suppression_rows = conn.execute(
            "SELECT COUNT(*) c FROM commercial_email_signal_fact WHERE signal_kind='suppression'"
        ).fetchone()["c"]
        positive_rows = conn.execute(
            "SELECT COUNT(*) c FROM commercial_email_signal_fact WHERE signal_kind='positive'"
        ).fetchone()["c"]

        missing_org_rollup = conn.execute(
            """
            SELECT COUNT(*) c
            FROM (
              SELECT DISTINCT org_domain
              FROM commercial_email_signal_fact
              WHERE org_domain IS NOT NULL AND length(trim(org_domain)) > 0
            ) f
            LEFT JOIN commercial_org_signal_rollup r ON r.org_domain = f.org_domain
            WHERE r.org_domain IS NULL
            """
        ).fetchone()["c"]
        missing_contact_rollup = conn.execute(
            """
            SELECT COUNT(*) c
            FROM (
              SELECT DISTINCT contact_email
              FROM commercial_email_signal_fact
              WHERE contact_email IS NOT NULL AND length(trim(contact_email)) > 0
            ) f
            LEFT JOIN commercial_contact_signal_rollup r ON r.contact_email = f.contact_email
            WHERE r.contact_email IS NULL
            """
        ).fetchone()["c"]

        print(f"DB: {db_path}")
        print(f"emails_total={total_emails}")
        print(f"emails_considered_in_facts={considered_emails}")
        print(f"signal_rows={fact_rows} positive_rows={positive_rows} suppression_rows={suppression_rows}")
        print(f"org_rollups={org_rollups} contact_rollups={contact_rollups} opportunity_facts={opportunity_facts}")
        print(
            "candidate_counts="
            f"org:{org_candidates} contact:{contact_candidates} opportunity:{opportunity_candidates}"
        )
        print(
            "reconciliation="
            f"missing_org_rollup:{missing_org_rollup} missing_contact_rollup:{missing_contact_rollup}"
        )

        if missing_org_rollup > 0 or missing_contact_rollup > 0:
            print("FAIL: rollup reconciliation gaps found.", file=sys.stderr)
            return 2
        if args.strict and positive_rows == 0:
            print("FAIL: no positive signals found under --strict.", file=sys.stderr)
            return 3
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

