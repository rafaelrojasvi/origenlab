#!/usr/bin/env python3
"""Export lead_master to CSV, optionally with match info (already_in_archive_flag, matched_org_name)."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_export_queries import (
    sql_left_join_best_org_match,
    sql_upstream_active_lead_master,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

_LM_UPSTREAM_ACTIVE = sql_upstream_active_lead_master("lm")
_JOIN_BEST_ORG = sql_left_join_best_org_match(variant="org_and_archive")

EXPORT_COLS = [
    "id_lead",
    "source_name", "org_name", "contact_name", "email", "phone", "website", "domain",
    "region", "city", "lead_type", "organization_type_guess", "equipment_match_tags",
    "lab_context_score", "lab_context_tags", "buyer_kind", "fit_bucket",
    "priority_score", "priority_reason", "evidence_summary", "status", "review_owner",
    "next_action", "source_url", "matched_org_name", "already_in_archive_flag",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Export leads to CSV")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV path")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)
    # Left join to one match per lead (first by id)
    rows = conn.execute(
        f"""
        SELECT
          lm.id AS id_lead,
          lm.source_name, lm.org_name, lm.contact_name, lm.email, lm.phone, lm.website, lm.domain,
          lm.region, lm.city, lm.lead_type, lm.organization_type_guess, lm.equipment_match_tags,
          lm.lab_context_score, lm.lab_context_tags, lm.buyer_kind, COALESCE(lm.fit_bucket,'low_fit') as fit_bucket,
          lm.priority_score, lm.priority_reason, lm.evidence_summary, lm.status, lm.review_owner,
          lm.next_action, lm.source_url,
          m.matched_org_name,
          COALESCE(m.already_in_archive_flag, 0)
        FROM lead_master lm
        {_JOIN_BEST_ORG}
        WHERE {_LM_UPSTREAM_ACTIVE}
        ORDER BY lm.priority_score DESC, lm.last_seen_at DESC
        """
    ).fetchall()
    conn.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(EXPORT_COLS)
        w.writerows(rows)
    print(f"Exported {len(rows)} leads to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
