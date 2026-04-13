#!/usr/bin/env python3
"""Export the next N lead contacts for cold outreach (``lead_master`` only).

Uses ``compute_next_marketing_recipients`` → shared ``candidate_export_gate.evaluate_export_eligibility``
(same as Streamlit **Cola outreach marketing**). Automatic exclusions, in order:

- Invalid email / internal domains (default block: ``origenlab.cl``, ``labdelivery.cl``).
- ``contact_email_suppression`` (if the table exists).
- Parsed To/Cc recipients on **Sent** mail in ``emails`` where ``source_file`` matches
  ``gmail:{mailbox}/%`` and ``folder`` is one of the configured Sent labels (defaults:
  ``[Gmail]/Enviados``, ``[Gmail]/Sent Mail``)—must match ingest from
  ``05_workspace_gmail_imap_to_sqlite.py``.
- ``outreach_contact_state`` for ``contacted``, ``replied``, or ``snoozed`` (if the table exists).
- Supplier domains from SQLite + marketing noise heuristics (unless disabled in code paths that
  support it; this CLI keeps them **on**).

Output CSV columns work with ``prepare_origenlab_marketing_outreach_input.py --input`` and
optional ``--pilot-csv`` for ``run_tatiana_pilot_batch.py``.
"""

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
from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_EXCLUDE_DOMAINS,
    DEFAULT_SENT_FOLDERS,
)
from origenlab_email_pipeline.next_marketing_queue import compute_next_marketing_recipients
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_TYPES,
    build_marketing_outreach_seed_body,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Export lead contacts for the next marketing batch, excluding addresses "
            "already present on ingested Sent mail (and optional suppression / outreach state)."
        )
    )
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV path")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--limit", type=int, default=40, help="Target unique recipient emails (default: 40)")
    ap.add_argument(
        "--fetch-cap",
        type=int,
        default=4000,
        help="Max lead rows to scan before stopping (default: 4000)",
    )
    ap.add_argument("--include-low-fit", action="store_true", help="Include low_fit (default: exclude)")
    ap.add_argument(
        "--min-priority",
        type=float,
        default=None,
        help="If set, require lead_master.priority_score >= this value",
    )
    ap.add_argument(
        "--gmail-user",
        type=str,
        default="",
        help="Mailbox login for Sent scan (default: ORIGENLAB_GMAIL_WORKSPACE_USER or contacto@origenlab.cl)",
    )
    ap.add_argument(
        "--sent-folder",
        action="append",
        default=[],
        help=(
            "IMAP folder label as stored in emails.folder / source_file. "
            "Repeatable. Defaults: [Gmail]/Enviados and [Gmail]/Sent Mail"
        ),
    )
    ap.add_argument(
        "--exclude-domain",
        action="append",
        default=[],
        help="Skip leads whose email domain equals this (repeatable). "
        "Defaults: origenlab.cl and labdelivery.cl",
    )
    ap.add_argument(
        "--pilot-csv",
        type=Path,
        default=None,
        help="Also write a pilot CSV for run_tatiana_pilot_batch.py --origenlab",
    )
    ap.add_argument(
        "--variant-type",
        type=str,
        default=MARKETING_VARIANT_GENERAL,
        help=f"Marketing variant for pilot CSV (default: {MARKETING_VARIANT_GENERAL})",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS

    extra_dom = tuple(args.exclude_domain) if args.exclude_domain else ()

    conn = connect(db_path)
    ensure_leads_tables(conn)
    export_rows, stats = compute_next_marketing_recipients(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        limit=int(args.limit),
        fetch_cap=int(args.fetch_cap),
        include_low_fit=bool(args.include_low_fit),
        min_priority=args.min_priority,
        extra_exclude_domains=extra_dom,
        variant_type=str(args.variant_type),
    )
    conn.close()

    summary_fields = [
        "case_id",
        "id_lead",
        "contact_email",
        "recipient_name",
        "institution_name",
        "sector",
        "fit_bucket",
        "priority_score",
        "already_in_archive_flag",
        "source_name",
        "website",
        "evidence_summary",
        "variant_type",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary_fields, extrasaction="ignore")
        w.writeheader()
        for r in export_rows:
            w.writerow({k: r.get(k, "") for k in summary_fields})

    print(
        f"Wrote {len(export_rows)} rows to {args.out} "
        f"(scanned {stats.n_scanned} ranked leads; "
        f"excluded {stats.n_sent_folder_recipients} from Sent, {stats.n_suppressed} suppressed, "
        f"{stats.n_outreach_state} outreach state; mailbox {stats.gmail_user!r})"
    )

    if args.pilot_csv:
        inst_col = [
            "case_id",
            "subject",
            "body_text",
            "case_type",
            "recipient_name",
            "institution_name",
            "sector",
            "product_focus",
            "use_case",
            "variant_type",
            "contact_email",
            "custom_note",
            "notes_for_reviewer",
        ]
        args.pilot_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.pilot_csv.open("w", encoding="utf-8", newline="") as pf:
            pw = csv.DictWriter(pf, fieldnames=inst_col)
            pw.writeheader()
            for r in export_rows:
                inst = str(r["institution_name"] or "").strip()
                subj = f"Presentacion OrigenLab | {inst}" if inst else "Presentacion OrigenLab"
                vn = str(r.get("variant_type") or MARKETING_VARIANT_GENERAL)
                if vn not in MARKETING_VARIANT_TYPES:
                    vn = MARKETING_VARIANT_GENERAL
                note = f"id_lead={r['id_lead']} fit={r['fit_bucket']}"
                pw.writerow(
                    {
                        "case_id": r["case_id"],
                        "subject": subj,
                        "body_text": _pilot_seed_body(vn, r, inst),
                        "case_type": "marketing_outreach",
                        "recipient_name": r["recipient_name"],
                        "institution_name": inst,
                        "sector": r["sector"],
                        "product_focus": "",
                        "use_case": "",
                        "variant_type": vn,
                        "contact_email": r["contact_email"],
                        "custom_note": "",
                        "notes_for_reviewer": note,
                    }
                )
        print(f"Pilot CSV: {args.pilot_csv}")

    if len(export_rows) < int(args.limit):
        print(
            f"Warning: only {len(export_rows)} unique addresses matched "
            f"(raise --fetch-cap, relax filters, or refresh Sent ingest).",
            file=sys.stderr,
        )
        return 2
    return 0


def _pilot_seed_body(vn: str, r: dict, inst: str) -> str:
    return build_marketing_outreach_seed_body(
        variant_type=vn,
        recipient_name=str(r["recipient_name"] or "") or None,
        institution_name=inst or None,
        sector=str(r["sector"] or "") or None,
        product_focus=None,
        use_case=None,
        custom_note=None,
    )


if __name__ == "__main__":
    sys.exit(main())
