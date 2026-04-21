#!/usr/bin/env python3
"""Export operator-facing outbound gate audit CSV (read-only).

This command evaluates candidate rows through the shared gate implementation without changing
any blocker source-of-truth tables.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.candidate_export_gate import (  # noqa: E402
    REASON_DOMAIN_SUPPRESSION,
    REASON_INTERNAL_DOMAIN,
    REASON_INVALID_EMAIL,
    REASON_OUTREACH_CONTACTED,
    REASON_OUTREACH_REPLIED,
    REASON_OUTREACH_SNOOZED,
    REASON_SENT_HISTORY,
    REASON_SUPPRESSION,
    evaluate_export_eligibility,
    normalize_export_email,
)
from origenlab_email_pipeline.config import load_settings  # noqa: E402
from origenlab_email_pipeline.db import connect  # noqa: E402
from origenlab_email_pipeline.lead_export_queries import sql_upstream_active_lead_master  # noqa: E402
from origenlab_email_pipeline.outbound_core import (  # noqa: E402
    gate_context_for_archive_batch,
    gate_context_for_lead_master_export,
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def _bool_hit(reason: str, code: str) -> int:
    return 1 if reason == code else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="Output CSV path.")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config).")
    ap.add_argument("--limit", type=int, default=2000, help="Max candidates to evaluate (default: 2000).")
    ap.add_argument("--lane", choices=("lead", "archive"), default="lead", help="Candidate lane to audit.")
    ap.add_argument("--gmail-user", type=str, default=None, help="Mailbox context override.")
    ap.add_argument("--sent-folder", action="append", default=[], help="Sent folder label (repeatable).")
    ap.add_argument(
        "--eligible-only",
        action="store_true",
        help="Export only eligible rows (final_eligible=1).",
    )
    ap.add_argument(
        "--include-blocked",
        action="store_true",
        help="Explicit flag for clarity; blocked rows are included by default unless --eligible-only.",
    )
    args = ap.parse_args()

    if args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite file not found: {db_path}", file=sys.stderr)
        return 1

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    conn = connect(db_path)
    rows_out: list[dict[str, object]] = []
    try:
        if args.lane == "lead":
            ctx = gate_context_for_lead_master_export(
                conn, gmail_user=gmail_user, sent_folders=sent_folders
            )
            where = sql_upstream_active_lead_master("lm")
            cur = conn.execute(
                f"""
                SELECT
                  lm.id,
                  lm.email,
                  lm.email_norm,
                  lm.org_name,
                  lm.domain_norm,
                  lm.fit_bucket
                FROM lead_master lm
                WHERE {where}
                ORDER BY lm.last_seen_at DESC
                LIMIT ?
                """,
                (int(args.limit),),
            )
            candidates = [
                {
                    "lead_id": r[0],
                    "raw_email": str(r[2] or r[1] or "").strip(),
                    "organization_name": str(r[3] or "").strip(),
                    "organization_domain": str(r[4] or "").strip(),
                    "fit_bucket": str(r[5] or ""),
                }
                for r in cur
            ]
        else:
            ctx = gate_context_for_archive_batch(
                conn, gmail_user=gmail_user, sent_folders=sent_folders
            )
            cur = conn.execute(
                """
                SELECT
                  email,
                  organization_name_guess,
                  domain,
                  ''
                FROM contact_master
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (int(args.limit),),
            )
            candidates = [
                {
                    "lead_id": "",
                    "raw_email": str(r[0] or "").strip(),
                    "organization_name": str(r[1] or "").strip(),
                    "organization_domain": str(r[2] or "").strip(),
                    "fit_bucket": str(r[3] or ""),
                }
                for r in cur
            ]

        for c in candidates:
            raw_email = str(c["raw_email"])
            normalized = normalize_export_email(raw_email)
            eval_email = normalized if normalized else raw_email
            gres = evaluate_export_eligibility(
                contact_email=eval_email,
                institution_name=(str(c["organization_name"]) or None),
                ctx=ctx,
            )
            reason = gres.reasons[0] if gres.reasons else ""
            outreach_state = ""
            if normalized:
                outreach_state = str(ctx.outreach_state_by_email.get(normalized, ""))

            row = {
                "email": normalized or raw_email,
                "lead_id": c["lead_id"],
                "organization_name": c["organization_name"],
                "organization_domain": c["organization_domain"],
                "fit_bucket": c["fit_bucket"],
                "blocked_by_sent": _bool_hit(reason, REASON_SENT_HISTORY),
                "blocked_by_outreach_state": int(
                    reason in (REASON_OUTREACH_CONTACTED, REASON_OUTREACH_REPLIED, REASON_OUTREACH_SNOOZED)
                ),
                "outreach_state": outreach_state,
                "blocked_by_email_suppression": _bool_hit(reason, REASON_SUPPRESSION),
                "blocked_by_domain_suppression": _bool_hit(reason, REASON_DOMAIN_SUPPRESSION),
                "blocked_by_internal_domain": _bool_hit(reason, REASON_INTERNAL_DOMAIN),
                "blocked_by_invalid_email": _bool_hit(reason, REASON_INVALID_EMAIL),
                "final_eligible": int(gres.eligible),
                "exclusion_reason": reason,
            }
            if args.eligible_only and not bool(row["final_eligible"]):
                continue
            rows_out.append(row)
    finally:
        conn.close()

    fieldnames = [
        "email",
        "lead_id",
        "organization_name",
        "organization_domain",
        "fit_bucket",
        "blocked_by_sent",
        "blocked_by_outreach_state",
        "outreach_state",
        "blocked_by_email_suppression",
        "blocked_by_domain_suppression",
        "blocked_by_internal_domain",
        "blocked_by_invalid_email",
        "final_eligible",
        "exclusion_reason",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows_out:
            w.writerow(row)
    print(f"Wrote {len(rows_out)} gate audit rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

