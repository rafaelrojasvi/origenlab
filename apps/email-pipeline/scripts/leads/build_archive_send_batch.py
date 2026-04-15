#!/usr/bin/env python3
"""Canonical archive outbound batch: audit → shortlist → gate snapshot → commercial precheck → CSVs.

Use ``--audit-only`` for audit CSV + JSON only (no shortlist/precheck). See RUNBOOK / OUTBOUND_SOURCE_OF_TRUTH."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.archive_send_batch_builder import (
    BUILD_SUMMARY_JSON_NAME,
    build_archive_send_batch,
    refresh_sent_mailbox,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
    sent_folder_defaults_were_used,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--gmail-user",
        type=str,
        default=None,
        help="Mailbox for Sent-history gate (default: ORIGENLAB_GMAIL_WORKSPACE_USER or contacto@origenlab.cl).",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("reports/out/active/archive_send_batch"),
        help="Output directory for stable archive batch artifacts.",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--fetch-cap", type=int, default=20000, help="Archive source scan cap.")
    ap.add_argument("--audit-limit", type=int, default=500, help="Max audited archive rows.")
    ap.add_argument("--shortlist-limit", type=int, default=25, help="Max archive shortlist rows.")
    ap.add_argument(
        "--refresh-sent",
        action="store_true",
        help="Refresh mailbox Sent folder before running audit/build.",
    )
    ap.add_argument(
        "--sent-folder",
        action="append",
        default=[],
        help="Sent folder label for gate and optional refresh (repeatable).",
    )
    ap.add_argument(
        "--since-days",
        type=int,
        default=30,
        help="If --refresh-sent, refresh window in days.",
    )
    ap.add_argument(
        "--strict-contact-graph-noise",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use strict contact graph noise filtering (default: true).",
    )
    ap.add_argument(
        "--allow-weak-warmth",
        action="store_true",
        help="Include weak-warmth archive candidates in shortlist (review-required downstream).",
    )
    ap.add_argument(
        "--skip-commercial-precheck",
        action="store_true",
        help="Debug-only bypass for commercial precheck; defaults to running precheck.",
    )
    ap.add_argument(
        "--route-personal-domain-with-client-signals-to-review",
        action="store_true",
        help=(
            "If enabled, free-personal-domain contacts with invoice/purchase signals are "
            "forced to review_required (never auto-send)."
        ),
    )
    ap.add_argument(
        "--audit-only",
        action="store_true",
        help=(
            "Write only archive_outreach_audit.csv and archive_outreach_audit_summary.json "
            "(plus a small build summary). Same audit logic as a full batch; no shortlist/precheck."
        ),
    )
    ap.add_argument(
        "--strict-commercial-drop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "When commercial precheck recommends drop (intel suppressed/rejected), treat as final "
            "drop and omit from send_ready/review CSVs. Default false: advisory — those rows go "
            "to review_required (shared export gate remains the only hard blocker for gate-eligible "
            "addresses)."
        ),
    )
    ap.add_argument(
        "--exclude-domain",
        action="append",
        default=[],
        help="Extra blocked domains for gate context (repeatable).",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folder_defaults_used = sent_folder_defaults_were_used(args.sent_folder)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)
    extra_exclude_domains = tuple(args.exclude_domain) if args.exclude_domain else ()

    if args.refresh_sent:
        refresh_sent_mailbox(
            project_root=_ROOT,
            db_path=db_path,
            sent_folder=sent_folders[0],
            since_days=int(args.since_days),
        )

    conn = connect(db_path)
    try:
        result = build_archive_send_batch(
            conn=conn,
            db_path=db_path,
            out_dir=args.out_dir,
            gmail_user=gmail_user,
            fetch_cap=int(args.fetch_cap),
            audit_limit=int(args.audit_limit),
            shortlist_limit=int(args.shortlist_limit),
            sent_folders=sent_folders,
            strict_contact_graph_noise=bool(args.strict_contact_graph_noise),
            allow_weak_warmth=bool(args.allow_weak_warmth),
            skip_commercial_precheck=bool(args.skip_commercial_precheck),
            route_personal_domain_with_client_signals_to_review=bool(
                args.route_personal_domain_with_client_signals_to_review
            ),
            audit_only=bool(args.audit_only),
            strict_commercial_drop=bool(args.strict_commercial_drop),
            extra_exclude_domains=extra_exclude_domains,
            sent_folder_defaults_used=sent_folder_defaults_used,
        )
    finally:
        conn.close()

    if args.audit_only:
        print(f"Wrote archive audit-only artifacts to {result.out_dir}")
    else:
        print(f"Wrote archive send batch to {result.out_dir}")
    print(f"Summary: {result.out_dir / BUILD_SUMMARY_JSON_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

