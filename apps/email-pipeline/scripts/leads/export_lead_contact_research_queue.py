#!/usr/bin/env python3
"""Export high/medium-fit lead queue for manual contact research (DeepSearch/ChatGPT).

Read-only: this script only exports CSV and summary counts; it does not mutate SQLite.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_export_queries import sql_upstream_active_lead_master

_DEFAULT_FIT = ("high_fit", "medium_fit")
_FIELDNAMES = [
    "lead_id",
    "organization_name",
    "organization_domain",
    "website",
    "region",
    "city",
    "fit_bucket",
    "priority_score",
    "current_lead_email",
    "current_email_norm",
    "contact_research_status",
    "resolved_contact_email",
    "resolved_domain",
    "needs_contact_research",
    "research_query_1",
    "research_query_2",
    "research_query_3",
    "notes",
]


def _fit_rank(fit: str) -> int:
    f = (fit or "").strip().lower()
    if f == "high_fit":
        return 0
    if f == "medium_fit":
        return 1
    return 2


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _mk_query(org_name: str, domain: str) -> tuple[str, str, str]:
    org = (org_name or "").strip()
    q1 = f"{org} contacto compras laboratorio".strip()
    q2 = f"{org} adquisiciones correo".strip()
    d = (domain or "").strip().lower()
    q3 = f"site:{d} contacto compras" if d else ""
    return q1, q2, q3


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="Output CSV path.")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config).")
    ap.add_argument("--limit", type=int, default=2000, help="Max rows to export (default: 2000).")
    ap.add_argument(
        "--fit",
        type=str,
        default="high_fit,medium_fit",
        help="Comma-separated fit buckets (default: high_fit,medium_fit).",
    )
    ap.add_argument(
        "--needs-research-only",
        type=str,
        default="true",
        help="When true (default), export only rows needing contact research.",
    )
    ap.add_argument(
        "--include-existing-research",
        action="store_true",
        help="Include leads that already have a valid resolved researched email.",
    )
    ap.add_argument(
        "--order",
        choices=("priority_score", "fit_then_recent", "lead_id"),
        default="fit_then_recent",
        help="Row ordering (default: fit_then_recent).",
    )
    args = ap.parse_args()

    if args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2

    fit_buckets = tuple(x.strip() for x in str(args.fit or "").split(",") if x.strip())
    if not fit_buckets:
        fit_buckets = _DEFAULT_FIT
    needs_only = _truthy(args.needs_research_only)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite file not found: {db_path}", file=sys.stderr)
        return 1

    where = sql_upstream_active_lead_master("lm")
    order_sql = {
        "priority_score": "ORDER BY (lm.priority_score IS NULL), lm.priority_score DESC, lm.id DESC",
        "fit_then_recent": (
            "ORDER BY CASE COALESCE(lm.fit_bucket, 'low_fit') "
            "WHEN 'high_fit' THEN 0 WHEN 'medium_fit' THEN 1 ELSE 2 END, "
            "lm.last_seen_at DESC, lm.id DESC"
        ),
        "lead_id": "ORDER BY lm.id ASC",
    }[args.order]

    fit_placeholders = ",".join("?" for _ in fit_buckets)
    sql = f"""
    SELECT
      lm.id,
      lm.org_name,
      lm.domain_norm,
      lm.website,
      lm.region,
      lm.city,
      COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
      lm.priority_score,
      lm.email,
      lm.email_norm,
      lcr.contact_research_status,
      lcr.resolved_contact_email,
      lcr.resolved_domain
    FROM lead_master lm
    LEFT JOIN lead_contact_research lcr ON lcr.lead_id = lm.id
    WHERE {where}
      AND COALESCE(lm.fit_bucket, 'low_fit') IN ({fit_placeholders})
    {order_sql}
    """

    conn = connect(db_path)
    try:
        rows = conn.execute(sql, fit_buckets).fetchall()
    finally:
        conn.close()

    total_scanned = len(rows)
    already_has_lead_email = 0
    already_has_researched_email = 0
    high_fit_missing = 0
    medium_fit_missing = 0
    out_rows: list[dict[str, object]] = []

    for r in rows:
        lead_id = int(r[0])
        org_name = str(r[1] or "").strip()
        domain = str(r[2] or "").strip().lower()
        website = str(r[3] or "").strip()
        region = str(r[4] or "").strip()
        city = str(r[5] or "").strip()
        fit_bucket = str(r[6] or "low_fit")
        priority_score = r[7]
        lead_email = str(r[8] or "").strip()
        lead_email_norm = str(r[9] or "").strip()
        research_status = str(r[10] or "").strip()
        researched_email = str(r[11] or "").strip()
        resolved_domain = str(r[12] or "").strip().lower()

        lead_valid = normalize_export_email(lead_email_norm or lead_email) is not None
        researched_valid = normalize_export_email(researched_email) is not None
        needs_research = not lead_valid and not researched_valid

        if lead_valid:
            already_has_lead_email += 1
        if researched_valid:
            already_has_researched_email += 1
        if needs_research and fit_bucket == "high_fit":
            high_fit_missing += 1
        if needs_research and fit_bucket == "medium_fit":
            medium_fit_missing += 1

        if researched_valid and not args.include_existing_research:
            continue
        if needs_only and not needs_research and not (args.include_existing_research and researched_valid):
            continue

        q1, q2, q3 = _mk_query(org_name, domain or resolved_domain)
        out_rows.append(
            {
                "lead_id": lead_id,
                "organization_name": org_name,
                "organization_domain": domain,
                "website": website,
                "region": region,
                "city": city,
                "fit_bucket": fit_bucket,
                "priority_score": priority_score if priority_score is not None else "",
                "current_lead_email": lead_email,
                "current_email_norm": lead_email_norm,
                "contact_research_status": research_status,
                "resolved_contact_email": researched_email,
                "resolved_domain": resolved_domain,
                "needs_contact_research": 1 if needs_research else 0,
                "research_query_1": q1,
                "research_query_2": q2,
                "research_query_3": q3,
                "notes": "",
            }
        )

        if len(out_rows) >= int(args.limit):
            break

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        w.writeheader()
        for row in out_rows:
            w.writerow(row)

    print(f"Wrote {len(out_rows)} research queue rows to {args.out}")
    print(f"total scanned: {total_scanned}")
    print(f"exported queue rows: {len(out_rows)}")
    print(f"high_fit missing contact: {high_fit_missing}")
    print(f"medium_fit missing contact: {medium_fit_missing}")
    print(f"already has lead email: {already_has_lead_email}")
    print(f"already has researched email: {already_has_researched_email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

