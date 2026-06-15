#!/usr/bin/env python3
"""Publish ChileCompra API equipment queue as canonical dashboard operator CSV."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from origenlab_email_pipeline.equipment_first_chilecompra_publish import (
    default_canonical_operator_queue_path,
    publish_chilecompra_equipment_queue_for_dashboard,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTIVE = ROOT / "reports/out/active/current"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Publish ChileCompra API equipment queue CSV as canonical "
            "equipment_first_operator_queue_*.csv for dashboard/API read models."
        ),
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        required=True,
        help="Path to equipment_first_operator_queue_chilecompra_api_YYYYMMDD.csv",
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=None,
        help="Optional ChileCompra API manifest JSON for publish metadata",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output canonical operator queue CSV (default: equipment_first_operator_queue_YYYYMMDD.csv)",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_ACTIVE.parent.parent,
        help="Reports root (parent of active/current)",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Prepend published queue to active/current/manifest.json canonical_files",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    out_csv = args.out or default_canonical_operator_queue_path(args.reports_dir, now=now)
    active_current = out_csv.parent

    try:
        result = publish_chilecompra_equipment_queue_for_dashboard(
            source_csv=args.source_csv,
            out_csv=out_csv,
            source_manifest=args.source_manifest,
            update_manifest=args.update_manifest,
            active_current=active_current,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Published {result['out_csv']}")
    print(f"input_rows={result['input_rows']}")
    print(f"output_rows={result['output_rows']}")
    if result.get("manifest_updated"):
        print(f"manifest_updated={result['manifest_path']}")
        print(f"canonical_files={result['canonical_files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
