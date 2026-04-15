#!/usr/bin/env python3
"""Export a client-friendly CSV: external leads + comparison to existing archive contacts.

Goal: give the client an easy weekly sheet with:
- what the lead is (buyer/title/context/tags)
- why it is relevant (priority_reason + evidence)
- whether OrigenLab already has history (matched org + existing contacts)
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_export_queries import (
    sql_cte_best_org_match,
    sql_upstream_active_lead_master,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

_LM_UPSTREAM_ACTIVE = sql_upstream_active_lead_master("lm")
_CTE_BEST_MATCH = sql_cte_best_org_match("best_match", variant="org_domain_archive")


EXPORT_COLS = [
    "id_lead",
    "fit_bucket",
    "priority_score",
    "priority_reason",
    "org_name",
    "contact_name",
    "lead_email",
    "lead_phone",
    "lead_website",
    "buyer_kind",
    "region",
    "city",
    "equipment_match_tags",
    "lab_context_score",
    "lab_context_tags",
    "evidence_summary",
    "source_url",
    "already_in_archive_flag",
    "matched_org_name",
    "matched_domain",
    "existing_key_contacts",
    "existing_top_contact_emails",
    "existing_total_emails",
    "existing_quote_email_count",
    "status",
    "review_owner",
    "next_action",
    "notes",
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="Export client review CSV from lead_master + matches + mart contacts")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV path")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--only-shortlist", action="store_true", help="Only export high_fit + medium_fit (default: true)")
    ap.add_argument("--limit", type=int, default=250, help="Max rows (default: 250)")
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)

    has_mart = _table_exists(conn, "organization_master") and _table_exists(conn, "contact_master")

    # One mart match row per lead: same rule as other exports (lowest lead_matches_existing_orgs.id).
    # If there is no match, archive fields are blank/0.
    if has_mart:
        sql = f"""
        WITH {_CTE_BEST_MATCH},
        top_contacts AS (
          SELECT
            domain,
            GROUP_CONCAT(email, '; ') AS emails
          FROM (
            SELECT email, domain
            FROM contact_master
            WHERE domain IS NOT NULL AND length(trim(domain)) > 0
            ORDER BY quote_email_count DESC, total_emails DESC, last_seen_at DESC
          )
          GROUP BY domain
        )
        SELECT
          lm.id AS id_lead,
          COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
          lm.priority_score,
          lm.priority_reason,
          lm.org_name,
          lm.contact_name,
          lm.email AS lead_email,
          lm.phone AS lead_phone,
          lm.website AS lead_website,
          lm.buyer_kind,
          lm.region,
          lm.city,
          lm.equipment_match_tags,
          lm.lab_context_score,
          lm.lab_context_tags,
          lm.evidence_summary,
          lm.source_url,
          COALESCE(bm.already_in_archive_flag, 0) AS already_in_archive_flag,
          bm.matched_org_name,
          bm.matched_domain,
          om.key_contacts AS existing_key_contacts,
          tc.emails AS existing_top_contact_emails,
          om.total_emails AS existing_total_emails,
          om.quote_email_count AS existing_quote_email_count,
          lm.status,
          lm.review_owner,
          lm.next_action,
          lm.notes
        FROM lead_master lm
        LEFT JOIN best_match bm ON bm.lead_id = lm.id
        LEFT JOIN organization_master om ON om.domain = bm.matched_domain
        LEFT JOIN top_contacts tc ON tc.domain = bm.matched_domain
        WHERE {_LM_UPSTREAM_ACTIVE}
          AND ((? = 0) OR (COALESCE(lm.fit_bucket,'low_fit') != 'low_fit'))
        ORDER BY
          CASE COALESCE(lm.fit_bucket, 'low_fit')
            WHEN 'high_fit' THEN 0
            WHEN 'medium_fit' THEN 1
            ELSE 2
          END,
          COALESCE(bm.already_in_archive_flag, 0) ASC,
          COALESCE(lm.priority_score, 0) DESC,
          CASE WHEN lm.equipment_match_tags IS NOT NULL AND length(trim(lm.equipment_match_tags)) > 0 THEN 0 ELSE 1 END,
          COALESCE(lm.lab_context_score, 0) DESC,
          lm.last_seen_at DESC
        LIMIT ?
        """
    else:
        sql = f"""
        SELECT
          lm.id AS id_lead,
          COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
          lm.priority_score,
          lm.priority_reason,
          lm.org_name,
          lm.contact_name,
          lm.email AS lead_email,
          lm.phone AS lead_phone,
          lm.website AS lead_website,
          lm.buyer_kind,
          lm.region,
          lm.city,
          lm.equipment_match_tags,
          lm.lab_context_score,
          lm.lab_context_tags,
          lm.evidence_summary,
          lm.source_url,
          0 AS already_in_archive_flag,
          '' AS matched_org_name,
          '' AS matched_domain,
          '' AS existing_key_contacts,
          '' AS existing_top_contact_emails,
          NULL AS existing_total_emails,
          NULL AS existing_quote_email_count,
          lm.status,
          lm.review_owner,
          lm.next_action,
          lm.notes
        FROM lead_master lm
        WHERE {_LM_UPSTREAM_ACTIVE}
          AND ((? = 0) OR (COALESCE(lm.fit_bucket,'low_fit') != 'low_fit'))
        ORDER BY
          CASE COALESCE(lm.fit_bucket, 'low_fit')
            WHEN 'high_fit' THEN 0
            WHEN 'medium_fit' THEN 1
            ELSE 2
          END,
          COALESCE(lm.priority_score, 0) DESC,
          CASE WHEN lm.equipment_match_tags IS NOT NULL AND length(trim(lm.equipment_match_tags)) > 0 THEN 0 ELSE 1 END,
          COALESCE(lm.lab_context_score, 0) DESC,
          lm.last_seen_at DESC
        LIMIT ?
        """

    rows = conn.execute(sql, (1 if args.only_shortlist else 0, args.limit)).fetchall()
    conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(EXPORT_COLS)
        w.writerows(rows)

    print(f"Exported client review CSV ({len(rows)} rows) to {args.out}")
    if not has_mart:
        print("Note: business mart tables not found; archive comparison columns are blank.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

