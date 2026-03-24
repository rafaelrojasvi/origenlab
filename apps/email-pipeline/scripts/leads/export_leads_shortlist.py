#!/usr/bin/env python3
"""Export a weekly review shortlist CSV (high-fit and medium-fit first)."""

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
    "source_name",
    "org_name",
    "contact_name",
    "email",
    "website",
    "region",
    "city",
    "lead_type",
    "buyer_kind",
    "organization_type_guess",
    "equipment_match_tags",
    "lab_context_score",
    "lab_context_tags",
    "priority_score",
    "priority_reason",
    "fit_bucket",
    "evidence_summary",
    "status",
    "review_owner",
    "next_action",
    "matched_org_name",
    "already_in_archive_flag",
    "source_url",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Export weekly shortlist CSV for review")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV path")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--include-low", action="store_true", help="Include low_fit rows (default: exclude)")
    ap.add_argument("--limit", type=int, default=250, help="Max rows in shortlist (default: 250)")
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)

    # Join to a single match row (if any) + flag net-new.
    rows = conn.execute(
        f"""
        SELECT
          lm.id AS id_lead,
          lm.source_name, lm.org_name, lm.contact_name, lm.email, lm.website,
          lm.region, lm.city, lm.lead_type, lm.buyer_kind, lm.organization_type_guess,
          lm.equipment_match_tags, lm.lab_context_score, lm.lab_context_tags,
          lm.priority_score, lm.priority_reason, COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
          lm.evidence_summary, lm.status, lm.review_owner, lm.next_action,
          m.matched_org_name, COALESCE(m.already_in_archive_flag, 0) AS already_in_archive_flag,
          lm.source_url
        FROM lead_master lm
        {_JOIN_BEST_ORG}
        WHERE
          {_LM_UPSTREAM_ACTIVE}
          AND ((? = 1) OR (COALESCE(lm.fit_bucket, 'low_fit') != 'low_fit'))
        ORDER BY
          CASE COALESCE(lm.fit_bucket, 'low_fit')
            WHEN 'high_fit' THEN 0
            WHEN 'medium_fit' THEN 1
            ELSE 2
          END,
          COALESCE(m.already_in_archive_flag, 0) ASC,
          COALESCE(lm.priority_score, 0) DESC,
          CASE WHEN lm.equipment_match_tags IS NOT NULL AND length(trim(lm.equipment_match_tags)) > 0 THEN 0 ELSE 1 END,
          COALESCE(lm.lab_context_score, 0) DESC,
          lm.last_seen_at DESC
        LIMIT ?
        """,
        (1 if args.include_low else 0, args.limit),
    ).fetchall()
    conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(EXPORT_COLS)
        w.writerows(rows)

    print(f"Exported shortlist ({len(rows)} rows) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

