#!/usr/bin/env python3
"""Export cold-outreach candidates from ``contact_master`` (exploratory / advanced lane).

Default: **audit-only** — evaluates candidates and prints counts; pass ``--export`` to write CSVs.
Not a daily outbound lane and **not send approval**.

Filters:
- Same Sent / suppression / outreach_contact_state exclusions as lead export
  (``contacted``, ``replied``, and ``snoozed`` block via shared ``candidate_export_gate``).
- ``marketing_contact_noise``: platforms, carriers, noreply-style locals, etc.
- **Supplier domains** from ``supplier_master.domain_norm`` (proveedores you import —
  e.g. Ohaus). ``contact_master`` alone cannot tell buyer vs supplier.

Does **not** delete anything from SQLite — ``contact_master`` stays a faithful archive slice.
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
from origenlab_email_pipeline.contact_export_queries import (
    sql_contact_master_marketing_export_candidates,
)
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_NOISE_EMAIL,
    REASON_NOISE_ORGANIZATION,
    REASON_SUPPLIER_DOMAIN,
    evaluate_export_eligibility,
)
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_SENT_FOLDERS,
    build_marketing_export_gate_context,
    load_outreach_state_map,
    load_sent_recipient_norms,
    load_suppressed_norms,
)
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_TYPES,
    build_marketing_outreach_seed_body,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit or export marketing candidates from contact_master (audit-only by default)."
    )
    ap.add_argument(
        "--out",
        "-o",
        type=Path,
        default=None,
        help="Summary CSV path (required with --export to write).",
    )
    ap.add_argument(
        "--pilot-csv",
        type=Path,
        default=None,
        help="Pilot CSV for run_tatiana_pilot_batch.py (requires --export).",
    )
    ap.add_argument(
        "--export",
        action="store_true",
        help="Write --out (and optional --pilot-csv) marketing CSVs. Default is audit-only.",
    )
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--fetch-cap", type=int, default=50000)
    ap.add_argument("--gmail-user", type=str, default="")
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument("--exclude-domain", action="append", default=[])
    ap.add_argument(
        "--skip-noise-filter",
        action="store_true",
        help="Disable platform/carrier/noreply heuristics (not recommended).",
    )
    ap.add_argument(
        "--skip-supplier-domain-filter",
        action="store_true",
        help="Do not exclude emails whose domain is in supplier_master (proveedores).",
    )
    ap.add_argument("--variant-type", type=str, default=MARKETING_VARIANT_GENERAL)
    args = ap.parse_args()

    export_requested = bool(args.export)
    if args.pilot_csv and not export_requested:
        ap.error("--pilot-csv requires --export")
    if export_requested and args.out is None:
        ap.error("--export requires --out")

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS

    variant = str(args.variant_type).strip()
    if variant not in MARKETING_VARIANT_TYPES:
        variant = MARKETING_VARIANT_GENERAL

    extra_dom = tuple(args.exclude_domain) if args.exclude_domain else ()
    conn = connect(db_path)
    gate_ctx = build_marketing_export_gate_context(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        extra_exclude_domains=extra_dom,
        skip_noise_filter=bool(args.skip_noise_filter),
        skip_supplier_domain_filter=bool(args.skip_supplier_domain_filter),
        strict_contact_graph_noise=True,
    )
    sent = load_sent_recipient_norms(conn, gmail_user=gmail_user, sent_folders=sent_folders)
    supp = load_suppressed_norms(conn)
    outreach_map = load_outreach_state_map(conn)

    cur = conn.execute(
        sql_contact_master_marketing_export_candidates(),
        (int(args.fetch_cap),),
    )
    cols = [d[0] for d in cur.description]

    kept: list[dict[str, object]] = []
    seen: set[str] = set()
    noise_skipped = 0
    supplier_skipped = 0
    scanned = 0

    for row in cur:
        scanned += 1
        d = dict(zip(cols, row))
        email = str(d["contact_email"]).strip().lower()
        inst = str(d.get("institution_name") or "").strip()
        if not email or email in seen:
            continue
        gres = evaluate_export_eligibility(
            contact_email=email,
            institution_name=inst or None,
            ctx=gate_ctx,
        )
        if not gres.eligible:
            r0 = gres.reasons[0] if gres.reasons else ""
            if r0 == REASON_SUPPLIER_DOMAIN:
                supplier_skipped += 1
            elif r0 in (REASON_NOISE_EMAIL, REASON_NOISE_ORGANIZATION):
                noise_skipped += 1
            continue
        seen.add(email)
        kept.append(
            {
                "case_id": f"cm_{len(kept) + 1:05d}",
                "contact_email": email,
                "recipient_name": str(d["recipient_name"] or "").strip(),
                "institution_name": str(d["institution_name"] or "").strip(),
                "total_emails": d["total_emails"],
                "last_seen_at": d["last_seen_at"],
                "confidence_score": d["confidence_score"],
                "variant_type": variant,
            }
        )
        if len(kept) >= int(args.limit):
            break

    conn.close()

    stats_line = (
        f"candidates kept={len(kept)} scanned={scanned} noise_skipped={noise_skipped} "
        f"supplier_skipped={supplier_skipped} supplier_domains_loaded={len(gate_ctx.supplier_domains)} "
        f"sent={len(sent)} suppressed={len(supp)} outreach_blocked={len(outreach_map)}"
    )

    if export_requested:
        assert args.out is not None
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "case_id",
            "contact_email",
            "recipient_name",
            "institution_name",
            "total_emails",
            "last_seen_at",
            "confidence_score",
            "variant_type",
        ]
        with args.out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(kept)

        print(f"Wrote {len(kept)} rows to {args.out} ({stats_line})")

        if args.pilot_csv:
            pfields = [
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
                pw = csv.DictWriter(pf, fieldnames=pfields)
                pw.writeheader()
                for r in kept:
                    inst = str(r["institution_name"] or "").strip()
                    subj = f"Presentacion OrigenLab | {inst}" if inst else "Presentacion OrigenLab"
                    vn = str(r.get("variant_type") or variant)
                    if vn not in MARKETING_VARIANT_TYPES:
                        vn = MARKETING_VARIANT_GENERAL
                    pw.writerow(
                        {
                            "case_id": r["case_id"],
                            "subject": subj,
                            "body_text": build_marketing_outreach_seed_body(
                                variant_type=vn,
                                recipient_name=str(r["recipient_name"] or "") or None,
                                institution_name=inst or None,
                                sector=None,
                                product_focus=None,
                                use_case=None,
                                custom_note=None,
                            ),
                            "case_type": "marketing_outreach",
                            "recipient_name": r["recipient_name"],
                            "institution_name": inst,
                            "sector": "",
                            "product_focus": "",
                            "use_case": "",
                            "variant_type": vn,
                            "contact_email": r["contact_email"],
                            "custom_note": "",
                            "notes_for_reviewer": "source=contact_master export_marketing_from_contact_master.py",
                        }
                    )
            print(f"Pilot CSV: {args.pilot_csv}")
    else:
        print("Audit only: pass --export to write marketing CSVs.")
        if args.out is not None:
            print(f"Planned summary CSV: {args.out}")
        if args.pilot_csv is not None:
            print(f"Planned pilot CSV: {args.pilot_csv}")
        print(stats_line)

    if len(kept) < int(args.limit):
        print(
            f"Warning: only {len(kept)} rows (raise --fetch-cap or check filters).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
