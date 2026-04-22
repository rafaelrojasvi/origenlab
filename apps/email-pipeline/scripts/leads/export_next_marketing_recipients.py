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

**Preflight:** Fails closed (exit code 3) unless ``--allow-empty-sent-history`` if SQLite has no
matching Gmail Sent rows or Sent rows have no parseable ``recipients`` — Sent-based blocking cannot
be verified. See ``outbound_sent_preflight``.

Output CSV columns work with ``prepare_origenlab_marketing_outreach_input.py --input`` and
optional ``--pilot-csv`` for ``run_tatiana_pilot_batch.py``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.next_marketing_queue import compute_next_marketing_recipients
from origenlab_email_pipeline.outbound_core import (
    DEFAULT_EXCLUDE_DOMAINS,
    build_outbound_run_envelope,
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
    sent_folder_defaults_were_used,
)
from origenlab_email_pipeline.outbound_sent_preflight import (
    evaluate_sent_history_preflight,
    print_sent_preflight_failure_to_stderr,
    probe_sent_history,
    sent_preflight_summary_dict,
)
from origenlab_email_pipeline.postgres_outbound_audit import (
    OutboundAuditError,
    build_outbound_batch_payload,
    build_outbound_recipient_payloads,
    maybe_write_postgres_outbound_audit,
)
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_TYPES,
    build_marketing_outreach_seed_body,
)

_WS_RE = re.compile(r"\s+")
_MAX_EVIDENCE_SUMMARY_CHARS = 4000


def _sanitize_csv_text(value: object, *, max_len: int | None = None) -> str:
    """Normalize CSV cell text for terminal/spreadsheet safety."""
    s = str(value or "")
    if not s:
        return ""
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # Remove C0/C1 controls while keeping printable Unicode as-is.
    s = "".join((" " if (ord(ch) < 32 or 127 <= ord(ch) <= 159) else ch) for ch in s)
    s = _WS_RE.sub(" ", s).strip()
    if max_len is not None and max_len > 0 and len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def _sanitize_summary_row(row: dict[str, object], *, fieldnames: list[str]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k in fieldnames:
        v = row.get(k, "")
        if isinstance(v, str) or v is None:
            if k == "evidence_summary":
                out[k] = _sanitize_csv_text(v, max_len=_MAX_EVIDENCE_SUMMARY_CHARS)
            else:
                out[k] = _sanitize_csv_text(v)
        else:
            out[k] = v
    return out


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
    ap.add_argument(
        "--write-outbound-summary",
        action="store_true",
        help="Write <output_stem>_outbound_summary.json with shared outbound_run metadata (lane=lead).",
    )
    ap.add_argument(
        "--allow-empty-sent-history",
        action="store_true",
        help=(
            "Allow export when no Gmail Sent rows match, or Sent rows have no parseable recipients. "
            "Dangerous: Sent-based already-contacted blocking may be ineffective. Prefer ingesting Sent."
        ),
    )
    ap.add_argument(
        "--write-postgres-audit",
        action="store_true",
        help="Optionally write outbound batch + recipients into Postgres outbound audit tables.",
    )
    ap.add_argument(
        "--postgres-url",
        type=str,
        default=None,
        help="Optional Postgres URL override for outbound audit write.",
    )
    ap.add_argument(
        "--audit-created-by",
        type=str,
        default=None,
        help="Optional actor string written to outbound.outbound_batch.created_by.",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_explicit = args.gmail_user.strip() if args.gmail_user and str(args.gmail_user).strip() else None
    gmail_user = resolve_outbound_gmail_user(settings, explicit=gmail_explicit)
    sent_folder_defaults_used = sent_folder_defaults_were_used(args.sent_folder)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    extra_dom = tuple(args.exclude_domain) if args.exclude_domain else ()

    conn = connect(db_path)
    ensure_leads_tables(conn)

    probe = probe_sent_history(conn, gmail_user=gmail_user, sent_folders=sent_folders)
    preflight = evaluate_sent_history_preflight(probe, allow_empty=bool(args.allow_empty_sent_history))
    if not preflight.ok:
        print_sent_preflight_failure_to_stderr(preflight)
        conn.close()
        return 3
    for w in preflight.warnings:
        print(f"warning: {w}", file=sys.stderr)

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

    if args.write_outbound_summary:
        summary_path = args.out.with_name(args.out.stem + "_outbound_summary.json")
        created = datetime.now(timezone.utc).isoformat()
        payload = {
            "outbound_run": build_outbound_run_envelope(
                lane="lead",
                gmail_user=gmail_user,
                sqlite_path=str(db_path),
                sent_folders=sent_folders,
                sent_folder_defaults_used=sent_folder_defaults_used,
                strict_contact_graph_noise=False,
                extra_exclude_domains=extra_dom,
                created_at_utc=created,
                artifact_paths={"marketing_csv": str(args.out.resolve())},
                counts={
                    "n_exported": len(export_rows),
                    "n_scanned": stats.n_scanned,
                    "n_sent_folder_recipients": stats.n_sent_folder_recipients,
                    "n_suppressed": stats.n_suppressed,
                    "n_outreach_state": stats.n_outreach_state,
                },
            ),
            "sent_preflight": sent_preflight_summary_dict(preflight),
            "lead_queue": {
                "limit_requested": int(args.limit),
                "fetch_cap": int(args.fetch_cap),
                "include_low_fit": bool(args.include_low_fit),
                "min_priority": args.min_priority,
            },
        }
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Outbound summary: {summary_path}")

    summary_fields = [
        "case_id",
        "id_lead",
        "contact_email",
        "email_source",
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
        w = csv.DictWriter(f, fieldnames=summary_fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in export_rows:
            w.writerow(_sanitize_summary_row(r, fieldnames=summary_fields))

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
            pw = csv.DictWriter(pf, fieldnames=inst_col, lineterminator="\n")
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
                        "case_id": _sanitize_csv_text(r["case_id"]),
                        "subject": _sanitize_csv_text(subj),
                        "body_text": _sanitize_csv_text(_pilot_seed_body(vn, r, inst)),
                        "case_type": "marketing_outreach",
                        "recipient_name": _sanitize_csv_text(r["recipient_name"]),
                        "institution_name": _sanitize_csv_text(inst),
                        "sector": _sanitize_csv_text(r["sector"]),
                        "product_focus": "",
                        "use_case": "",
                        "variant_type": _sanitize_csv_text(vn),
                        "contact_email": _sanitize_csv_text(r["contact_email"]),
                        "custom_note": "",
                        "notes_for_reviewer": _sanitize_csv_text(note),
                    }
                )
        print(f"Pilot CSV: {args.pilot_csv}")

    if len(export_rows) < int(args.limit):
        print(
            f"Warning: only {len(export_rows)} unique addresses matched "
            f"(raise --fetch-cap, relax filters, or refresh Sent ingest).",
            file=sys.stderr,
        )
        rc = 2
    else:
        rc = 0

    # Optional Postgres outbound audit writing; never required unless explicit flag.
    if args.write_postgres_audit:
        batch_payload = build_outbound_batch_payload(
            lane="lead",
            created_by=args.audit_created_by,
            gmail_user=gmail_user,
            sent_folders=list(sent_folders),
            sent_preflight_json=sent_preflight_summary_dict(preflight),
            gate_version="candidate_export_gate",
            output_artifact_path=str(args.out.resolve()),
            notes="lead export_next_marketing_recipients",
        )
        recipient_rows = []
        for r in export_rows:
            lead_id = r.get("id_lead")
            source_key = str(lead_id) if lead_id not in (None, "") else None
            recipient_rows.append(
                {
                    "email_norm": r.get("contact_email"),
                    "lead_id": lead_id,
                    "source_kind": "lead",
                    "source_key": source_key,
                    "organization_name": r.get("institution_name"),
                    "organization_domain": r.get("domain"),
                    "eligibility_result": "eligible",
                    "exclusion_reason": None,
                    "metadata_json": {
                        "case_id": r.get("case_id"),
                        "fit_bucket": r.get("fit_bucket"),
                        "priority_score": r.get("priority_score"),
                        "variant_type": r.get("variant_type"),
                        "source_name": r.get("source_name"),
                    },
                }
            )
        recipients_payload = build_outbound_recipient_payloads(recipient_rows)
        try:
            batch_id = maybe_write_postgres_outbound_audit(
                write_requested=True,
                explicit_postgres_url=args.postgres_url,
                batch=batch_payload,
                recipients=recipients_payload,
            )
        except OutboundAuditError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            f"Postgres outbound audit written: batch_id={batch_id} recipients={len(recipients_payload)}"
        )

    return rc


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
