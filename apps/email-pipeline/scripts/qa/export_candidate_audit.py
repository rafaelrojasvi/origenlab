#!/usr/bin/env python3
"""Read-only audit: export eligibility for lead path vs contact_master path (shared gate).

Does not write the database. Outputs CSV for QA (parity checks, leakage review).

Example::

  uv run python scripts/qa/export_candidate_audit.py --out /tmp/audit.csv --lead-limit 500 --contact-limit 500
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.candidate_export_gate import (
    REASON_INTERNAL_DOMAIN,
    REASON_NOISE_EMAIL,
    REASON_NOISE_ORGANIZATION,
    REASON_OUTREACH_CONTACTED,
    REASON_OUTREACH_REPLIED,
    REASON_OUTREACH_SNOOZED,
    REASON_SENT_HISTORY,
    REASON_SUPPLIER_DOMAIN,
    REASON_SUPPRESSION,
    evaluate_export_eligibility,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.contact_export_queries import (
    sql_contact_master_candidate_audit_contacts,
)
from origenlab_email_pipeline.lead_export_queries import (
    sql_left_join_best_org_match,
    sql_upstream_active_lead_master,
)
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_SENT_FOLDERS,
    build_marketing_export_gate_context,
    load_outreach_state_map,
    norm_lead_email,
)


def _reason_hits(reason: str) -> dict[str, bool]:
    return {
        "supplier_hit": reason == REASON_SUPPLIER_DOMAIN,
        "noise_email_hit": reason == REASON_NOISE_EMAIL,
        "noise_org_hit": reason == REASON_NOISE_ORGANIZATION,
        "suppression_hit": reason == REASON_SUPPRESSION,
        "sent_hit": reason == REASON_SENT_HISTORY,
        "internal_domain_hit": reason == REASON_INTERNAL_DOMAIN,
        "outreach_contacted_hit": reason == REASON_OUTREACH_CONTACTED,
        "outreach_replied_hit": reason == REASON_OUTREACH_REPLIED,
        "outreach_snoozed_hit": reason == REASON_OUTREACH_SNOOZED,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit export gate over lead + contact_master candidates (read-only)")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV path")
    ap.add_argument("--gmail-user", type=str, default="")
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument("--exclude-domain", action="append", default=[])
    ap.add_argument("--lead-limit", type=int, default=2000)
    ap.add_argument("--contact-limit", type=int, default=2000)
    ap.add_argument(
        "--skip-noise-filter",
        action="store_true",
        help="Match export_marketing_from_contact_master --skip-noise-filter",
    )
    ap.add_argument(
        "--skip-supplier-domain-filter",
        action="store_true",
        help="Match export_marketing_from_contact_master --skip-supplier-domain-filter",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        return 1

    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS
    extra_dom = tuple(args.exclude_domain) if args.exclude_domain else ()

    conn = connect(db_path)
    try:
        gate_ctx_lead = build_marketing_export_gate_context(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            extra_exclude_domains=extra_dom,
            skip_noise_filter=bool(args.skip_noise_filter),
            skip_supplier_domain_filter=bool(args.skip_supplier_domain_filter),
            strict_contact_graph_noise=False,
        )
        gate_ctx_contact = replace(
            gate_ctx_lead,
            strict_contact_graph_noise=True,
        )
        outreach_map = load_outreach_state_map(conn)

        lm_where = sql_upstream_active_lead_master("lm")
        join_org = sql_left_join_best_org_match(variant="org_and_archive")
        lead_sql = f"""
        SELECT
          lm.id AS id_lead,
          lm.email,
          lm.email_norm,
          lm.org_name,
          m.matched_org_name,
          COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket
        FROM lead_master lm
        {join_org}
        WHERE {lm_where}
          AND NULLIF(TRIM(COALESCE(lm.email_norm, lm.email)), '') IS NOT NULL
        ORDER BY
          CASE COALESCE(lm.fit_bucket, 'low_fit')
            WHEN 'high_fit' THEN 0
            WHEN 'medium_fit' THEN 1
            ELSE 2
          END,
          lm.last_seen_at DESC
        LIMIT ?
        """

        contact_sql = sql_contact_master_candidate_audit_contacts()

        rows_out: list[dict[str, object]] = []

        cur = conn.execute(lead_sql, (int(args.lead_limit),))
        for r in cur:
            id_lead, email_raw, email_norm, org_name, matched_org, fit_bucket = r
            em = norm_lead_email(
                str(email_norm) if email_norm else None,
                str(email_raw) if email_raw else None,
            )
            if not em:
                continue
            inst = (str(org_name or "").strip() or str(matched_org or "").strip())
            domain = em.split("@", 1)[-1] if "@" in em else ""
            gres = evaluate_export_eligibility(
                contact_email=em,
                institution_name=inst or None,
                ctx=gate_ctx_lead,
            )
            reason = gres.reasons[0] if gres.reasons else ""
            hits = _reason_hits(str(reason))
            rows_out.append(
                {
                    "source_path": "lead_master",
                    "email": em,
                    "domain": domain,
                    "institution_name": inst,
                    "fit_bucket": str(fit_bucket or ""),
                    "id_lead": id_lead,
                    "outreach_state": outreach_map.get(em, ""),
                    "eligible": int(gres.eligible),
                    "reject_reasons": reason,
                    **{k: int(v) for k, v in hits.items()},
                }
            )

        cur2 = conn.execute(contact_sql, (int(args.contact_limit),))
        for r in cur2:
            em, inst, fit_bucket, id_lead = r
            em = str(em or "").strip().lower()
            if not em:
                continue
            inst_s = str(inst or "").strip()
            domain = em.split("@", 1)[-1] if "@" in em else ""
            gres = evaluate_export_eligibility(
                contact_email=em,
                institution_name=inst_s or None,
                ctx=gate_ctx_contact,
            )
            reason = gres.reasons[0] if gres.reasons else ""
            hits = _reason_hits(str(reason))
            rows_out.append(
                {
                    "source_path": "contact_master",
                    "email": em,
                    "domain": domain,
                    "institution_name": inst_s,
                    "fit_bucket": str(fit_bucket or ""),
                    "id_lead": id_lead or "",
                    "outreach_state": outreach_map.get(em, ""),
                    "eligible": int(gres.eligible),
                    "reject_reasons": reason,
                    **{k: int(v) for k, v in hits.items()},
                }
            )
    finally:
        conn.close()

    fieldnames = [
        "source_path",
        "email",
        "domain",
        "institution_name",
        "fit_bucket",
        "id_lead",
        "supplier_hit",
        "noise_email_hit",
        "noise_org_hit",
        "suppression_hit",
        "outreach_contacted_hit",
        "outreach_replied_hit",
        "outreach_snoozed_hit",
        "sent_hit",
        "internal_domain_hit",
        "eligible",
        "reject_reasons",
        "outreach_state",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows_out:
            w.writerow(row)

    print(f"Wrote {len(rows_out)} audit rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
