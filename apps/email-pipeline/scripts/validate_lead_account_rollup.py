#!/usr/bin/env python3
"""Validate lead account rollup: counts, orphans, matches, samples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_upstream_reconcile import sql_upstream_active
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

_LM_UPSTREAM_ACTIVE = sql_upstream_active("lm")
from origenlab_email_pipeline.lead_accounts_schema import ensure_lead_account_tables


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate lead account rollup")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    settings = load_settings()
    conn = connect(args.db or settings.resolved_sqlite_path())
    ensure_leads_tables(conn)
    ensure_lead_account_tables(conn)

    n_leads = conn.execute(
        f"SELECT COUNT(*) FROM lead_master lm WHERE {_LM_UPSTREAM_ACTIVE}"
    ).fetchone()[0]
    n_accounts = conn.execute("SELECT COUNT(*) FROM lead_account_master").fetchone()[0]
    n_mem = conn.execute("SELECT COUNT(*) FROM lead_account_membership").fetchone()[0]
    n_alias = conn.execute("SELECT COUNT(*) FROM lead_account_aliases").fetchone()[0]
    n_match = conn.execute("SELECT COUNT(*) FROM lead_account_matches_existing_orgs").fetchone()[0]

    unmatched = conn.execute(
        f"""
        SELECT COUNT(*) FROM lead_master lm
        WHERE {_LM_UPSTREAM_ACTIVE}
          AND NOT EXISTS (SELECT 1 FROM lead_account_membership m WHERE m.lead_id = lm.id)
        """
    ).fetchone()[0]

    print("=== Counts ===")
    print(f"lead_master (upstream-active): {n_leads}")
    print(f"lead_account_master:      {n_accounts}")
    print(f"lead_account_membership:  {n_mem}")
    print(f"lead_account_aliases:     {n_alias}")
    print(f"matches -> organization:  {n_match}")
    print(f"leads with no membership: {unmatched}")
    print()

    print("=== Top accounts by lead_count ===")
    for row in conn.execute(
        """
        SELECT id, canonical_name, lead_count, primary_domain, quality_status
        FROM lead_account_master
        ORDER BY lead_count DESC
        LIMIT 15
        """
    ):
        print(f"  id={row[0]} count={row[2]} domain={row[3]!r} q={row[4]} name={row[1][:80]!r}")

    print()
    print("=== Accounts with multiple mart matches (should be rare) ===")
    multi = conn.execute(
        """
        SELECT lead_account_id, COUNT(*) FROM lead_account_matches_existing_orgs
        GROUP BY lead_account_id HAVING COUNT(*) > 1
        LIMIT 10
        """
    ).fetchall()
    if not multi:
        print("  (none)")
    else:
        for aid, c in multi:
            print(f"  account_id={aid} matches={c}")

    print()
    print("=== Sample high lead_count + needs_review quality ===")
    for row in conn.execute(
        """
        SELECT id, canonical_name, lead_count, primary_domain
        FROM lead_account_master
        WHERE quality_status = 'needs_review'
        ORDER BY lead_count DESC
        LIMIT 8
        """
    ):
        print(f"  id={row[0]} count={row[2]} dom={row[3]!r} {row[1][:70]!r}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
