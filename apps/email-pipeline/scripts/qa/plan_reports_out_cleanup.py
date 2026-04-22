#!/usr/bin/env python3
"""Read-only plan for `reports/out` tree (no delete/move; optional JSON report file).

Scans a directory, classifies paths into planning buckets, prints sizes and proposed actions.
Buckets include ``active_current``, ``active_workspace_misc`` (``active/`` but not
``active/current/``), ``client_pack_latest``, ``reference``, ``archive``, tmp/lab, etc.
Default root: apps/email-pipeline/reports/out (or pass --reports-out-dir).
Does not read SQLite, does not use Gmail, does not require secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_APP = Path(__file__).resolve().parents[2]
if str(_APP / "src") not in sys.path:
    sys.path.insert(0, str(_APP / "src"))

from origenlab_email_pipeline.core.reports_out import (
    FileEntry,
    PROPOSED_ACTION,
    PROPOSED_ACTION_PRINT_ORDER,
    by_bucket_aggregation,
    classify_path,
    normalize_reports_out_root,
    over_threshold_entries,
    scan_reports_out,
)

APP_ROOT = _APP
_DEFAULT_REPORTS_OUT = APP_ROOT / "reports" / "out"


def print_report(
    root: Path,
    entries: list[FileEntry],
    file_count: int,
    total_bytes: int,
    large_threshold: int,
    top_large: int,
) -> None:
    lines: list[str] = []
    lines.append(f"reports out root: {root.resolve()}")
    lines.append(f"total files: {file_count}")
    lines.append(f"total size: {total_bytes} bytes ({total_bytes / (1024*1024):.4f} MB)")
    lines.append(f"large file threshold: {large_threshold} bytes ({large_threshold / (1024*1024):.4f} MB)")

    agg = by_bucket_aggregation(entries)
    lines.append("--- by primary bucket (count, bytes) ---")
    for bucket, st in agg.items():
        lines.append(
            f"  {bucket}: {st['file_count']} files, {st['total_bytes']} bytes ({st['size_mb']} MB)"
        )
    n_large = sum(1 for e in entries if e.size_bytes >= large_threshold)
    b_large = sum(e.size_bytes for e in entries if e.size_bytes >= large_threshold)
    lines.append("--- over threshold (may overlap with buckets) ---")
    lines.append(
        f"  files over threshold: {n_large}, total bytes: {b_large} ({(b_large / (1024*1024)) if b_large else 0:.4f} MB)"
    )
    large_list = [e for e in entries if e.is_over_large_threshold]
    if large_list:
        lines.append(f"--- largest {top_large} files (by size) ---")
        for e in over_threshold_entries(entries, large_threshold, top_large):
            lines.append(
                f"  {e.size_bytes:12d} B  bucket={e.primary_bucket}  {e.relative_path}"
            )
    else:
        lines.append("--- no files at or over threshold ---")

    lines.append("--- proposed action (per bucket) ---")
    for bucket in PROPOSED_ACTION_PRINT_ORDER:
        a = PROPOSED_ACTION.get(bucket)
        if a is not None:
            lines.append(f"  {bucket}: {a}")
    lines.append("  (global) do not commit generated outputs; treat this tree as local/evidence")
    for line in lines:
        print(line, file=sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--reports-out-dir",
        type=Path,
        default=None,
        help="Root to scan (default: apps/email-pipeline/reports/out from this script location)",
    )
    p.add_argument(
        "--large-threshold-mb",
        type=float,
        default=5.0,
        help="Files at or over this size are flagged (default: 5 MB).",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="If set, write a JSON report to this path (does not modify reports out).",
    )
    p.add_argument(
        "--top",
        type=int,
        default=20,
        help="How many largest files to list (default: 20).",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    root = args.reports_out_dir
    if root is None:
        root = _DEFAULT_REPORTS_OUT
    root = normalize_reports_out_root(root)
    th_bytes = max(1, int(args.large_threshold_mb * 1024 * 1024 + 0.5))

    entries, file_count, total_bytes = scan_reports_out(root, th_bytes)
    print_report(
        root,
        entries,
        file_count,
        total_bytes,
        th_bytes,
        int(args.top),
    )

    if args.json_out is not None:
        path = args.json_out.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "reports_out_root": str(root),
            "file_count": file_count,
            "total_bytes": total_bytes,
            "large_threshold_bytes": th_bytes,
            "large_threshold_mb": args.large_threshold_mb,
            "by_bucket": by_bucket_aggregation(entries),
            "files": [asdict(e) for e in entries],
            "largest_at_or_over_threshold": [asdict(e) for e in over_threshold_entries(entries, th_bytes, 5000)],
            "proposed_action_per_bucket": {**PROPOSED_ACTION},
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote json report: {path}", file=sys.stdout)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
