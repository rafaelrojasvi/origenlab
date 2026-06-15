#!/usr/bin/env python3
"""Build equipment-first operator queue from Mercado Público licitaciones API."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from origenlab_email_pipeline.chilecompra_api import ChileCompraTicketMissingError
from origenlab_email_pipeline.equipment_first_chilecompra_queue import (
    build_equipment_queue_from_chilecompra_api,
    default_chilecompra_api_queue_csv_path,
    default_chilecompra_candidate_audit_path,
    write_candidate_audit_csv,
    write_chilecompra_api_queue_outputs,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS = ROOT / "reports/out/active/current"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Mercado Público licitaciones via API and build equipment-first queue CSV. "
            "Requires CHILECOMPRA_API_TICKET in the environment."
        ),
    )
    parser.add_argument("--estado", default="activas", help="API estado filter (default: activas)")
    parser.add_argument(
        "--fecha",
        default=None,
        help="Optional fecha filter in ddmmaaaa format",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=100,
        help="Maximum detail lookups after summary keyword prefilter (default: 100)",
    )
    parser.add_argument(
        "--detail-sleep-seconds",
        type=float,
        default=1.0,
        help="Pause between detail API lookups to reduce rate limiting (default: 1.0)",
    )
    parser.add_argument(
        "--fail-fast-detail-errors",
        action="store_true",
        help="Abort on the first detail lookup HTTP error instead of recording and continuing",
    )
    parser.add_argument(
        "--detail-cache-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory for per-codigo detail JSON cache "
            "(e.g. reports/out/active/current/chilecompra_detail_cache)"
        ),
    )
    parser.add_argument(
        "--write-candidate-audit",
        action="store_true",
        help="Write candidate audit CSV for prefilter/detail review",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default: equipment_first_operator_queue_chilecompra_api_YYYYMMDD.csv)",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS.parent.parent,
        help="Reports root (parent of active/current)",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    out_csv = args.out or default_chilecompra_api_queue_csv_path(args.reports_dir, now=now)

    try:
        rows, manifest, audit_rows = build_equipment_queue_from_chilecompra_api(
            estado=args.estado,
            fecha=args.fecha,
            max_details=args.max_details,
            detail_sleep_seconds=args.detail_sleep_seconds,
            continue_on_detail_error=not args.fail_fast_detail_errors,
            detail_cache_dir=args.detail_cache_dir,
            now=now,
        )
    except ChileCompraTicketMissingError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    stats = write_chilecompra_api_queue_outputs(rows=rows, manifest=manifest, out_csv=out_csv)
    print(f"Wrote {stats['out_csv']}")
    print(f"Manifest {stats['manifest_path']}")
    if args.write_candidate_audit:
        audit_path = default_chilecompra_candidate_audit_path(args.reports_dir, now=now)
        write_candidate_audit_csv(audit_rows, audit_path)
        print(f"Candidate audit {audit_path}")
    for key in (
        "fetched_summaries",
        "candidate_summaries",
        "detail_requests",
        "detail_cache_hits",
        "detail_cache_writes",
        "detail_error_count",
        "normalized_item_rows",
        "output_rows",
        "by_next_action",
    ):
        print(f"{key}: {stats[key]}")
    if stats.get("detail_error_count"):
        print(f"detail_error_codes: {stats.get('detail_error_codes', [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
