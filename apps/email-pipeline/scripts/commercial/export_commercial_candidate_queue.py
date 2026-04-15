#!/usr/bin/env python3
"""Export ``v_commercial_candidate_queue`` to CSV or JSON (filters + limit)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/...` from repo root or apps/email-pipeline.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.commercial.commercial_intel_review import (  # noqa: E402
    QueueFilters,
    fetch_queue_rows,
    write_export_file,
)
from origenlab_email_pipeline.config import load_settings  # noqa: E402
from origenlab_email_pipeline.db import connect  # noqa: E402
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="Output file path (.csv or .json).")
    ap.add_argument("--format", choices=("csv", "json"), default=None, help="Override format from extension.")
    ap.add_argument("--limit", type=int, default=500, help="Max rows (default 500).")
    ap.add_argument("--entity-kind", choices=("organization", "contact", "opportunity"), default=None)
    ap.add_argument(
        "--review-status",
        default=None,
        help="Filter by candidate status (e.g. needs_review, approved).",
    )
    ap.add_argument("--candidate-type", default=None, help="Organization candidate_type (e.g. net_new).")
    ap.add_argument("--min-confidence", type=float, default=None)
    ap.add_argument("--min-strength", type=float, default=None)
    ap.add_argument(
        "--order-by",
        default="confidence_score DESC, strength_score DESC",
        choices=(
            "confidence_score DESC, strength_score DESC",
            "strength_score DESC, confidence_score DESC",
            "updated_at DESC",
            "evidence_count DESC",
        ),
    )
    args = ap.parse_args()

    fmt = args.format
    if fmt is None:
        suf = args.out.suffix.lower()
        if suf == ".csv":
            fmt = "csv"
        elif suf == ".json":
            fmt = "json"
        else:
            ap.error("use --format or a .csv/.json output path")

    settings = load_settings()
    conn = connect(settings.resolved_sqlite_path())
    try:
        migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.COMMERCIAL_INTEL})
        filters = QueueFilters(
            entity_kind=args.entity_kind,
            review_status=args.review_status,
            candidate_type=args.candidate_type,
            min_confidence=args.min_confidence,
            min_strength=args.min_strength,
        )
        rows = fetch_queue_rows(conn, filters=filters, limit=args.limit, order_by=args.order_by)
    finally:
        conn.close()

    write_export_file(args.out, rows, fmt)
    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
