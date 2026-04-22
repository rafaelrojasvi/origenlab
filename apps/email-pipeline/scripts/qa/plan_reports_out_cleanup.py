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
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REPORTS_OUT = APP_ROOT / "reports" / "out"

FULL_RUN_PREFIX = re.compile(r"^full_\d{8}_\d{6}$", re.IGNORECASE)


def _norm(p: Path) -> Path:
    return p.resolve()


@dataclass(frozen=True, slots=True)
class FileEntry:
    relative_path: str
    size_bytes: int
    primary_bucket: str
    is_over_large_threshold: bool


def has_active_current(rel: Path) -> bool:
    parts = rel.parts
    for i in range(len(parts) - 1):
        if parts[i].casefold() == "active" and parts[i + 1].casefold() == "current":
            return True
    return False


def is_reference(rel: Path) -> bool:
    return len(rel.parts) >= 1 and rel.parts[0].casefold() == "reference"


def is_client_pack_latest(rel: Path) -> bool:
    return len(rel.parts) >= 1 and rel.parts[0].casefold() == "client_pack_latest"


def is_active_workspace_misc(rel: Path) -> bool:
    """``active/`` paths that are not under ``active/current/`` (see ``has_active_current``)."""
    if not rel.parts or rel.parts[0].casefold() != "active":
        return False
    return not has_active_current(rel)


def is_archive_path(rel: Path) -> bool:
    if not rel.parts:
        return False
    first = rel.parts[0].casefold()
    if first in ("archive", "_archive"):
        return True
    head = rel.parts[0]
    l = head.casefold()
    if l.startswith("archive_") or (l.startswith("old_") and "run" in l) or l.startswith("campaign_"):
        return True
    for part in rel.parts:
        if part.casefold() in ("_archive", "archived", "old_archive") or "archive" in part.casefold() and (
            "campaign" in part.casefold() or "backup" in part.casefold()
        ):
            return True
    return False


def is_lab_or_tatiana(rel: Path) -> bool:
    s = str(rel).casefold()
    if "tatiana" in s or "tati_" in s:
        return True
    for part in rel.parts:
        pl = part.casefold()
        if pl in ("ml", "ml_runs", "ml_reports", "email_ml", "llm") or "email_ml" in pl:
            return True
    return False


def is_tmp_or_scratch(rel: Path) -> bool:
    for i, part in enumerate(rel.parts):
        pl = part.casefold()
        if pl in ("tmp", "temp", ".tmp", "scratch", "ephemeral", "staged", "stg"):
            return True
        if pl.startswith("my_"):
            return True
        if i == 0 and (pl.startswith("test_") or pl.startswith("debug_") or pl.startswith("oneoff_")):
            return True
        if i == 0 and FULL_RUN_PREFIX.match(part):
            return True
    return False


def is_excluded_root_artifact(name: str) -> bool:
    n = name.casefold()
    return n in (".gitkeep", "readme.md", ".gitignore")


def classify_path(rel: Path) -> str:
    """Return primary bucket for a file path (relative to reports root)."""
    if not rel.parts:
        return "unknown"

    if is_excluded_root_artifact(rel.parts[0]) and len(rel.parts) == 1:
        return "repo_bootstrap"

    if has_active_current(rel):
        return "active_current"

    if is_active_workspace_misc(rel):
        return "active_workspace_misc"

    if is_client_pack_latest(rel):
        return "client_pack_latest"

    if is_reference(rel):
        return "reference"

    if is_archive_path(rel):
        return "archive"

    if is_lab_or_tatiana(rel):
        return "lab_or_tatiana"

    if is_tmp_or_scratch(rel):
        return "tmp_or_scratch"

    if len(rel.parts) == 1:
        n = rel.parts[0]
        if not is_excluded_root_artifact(n):
            if rel.suffix:  # file
                return "loose_root_files"
            return "unknown"

    return "unknown"


def scan_reports_out(
    root: Path,
    large_threshold_bytes: int,
) -> tuple[list[FileEntry], int, int]:
    root = _norm(root)
    if not root.is_dir():
        return [], 0, 0

    entries: list[FileEntry] = []
    total_size = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        rel = p.relative_to(root)
        b = classify_path(rel)
        sz = st.st_size
        total_size += sz
        over = sz >= large_threshold_bytes
        entries.append(
            FileEntry(
                relative_path=rel.as_posix(),
                size_bytes=sz,
                primary_bucket=b,
                is_over_large_threshold=over,
            )
        )
    n = len(entries)
    return entries, n, total_size


PROPOSED_ACTION: dict[str, str] = {
    "active_current": "keep active/current (canonical current campaign workspace)",
    "active_workspace_misc": "active/ but not current — batch exports, compare folders, ad-hoc workspace; not unknown",
    "client_pack_latest": "client pack snapshot; keep for handoff/evidence; do not auto-archive in daily lane",
    "archive": "archive / retain as historical; review before delete or move",
    "reference": "keep reference (intentional long-lived small evidence only)",
    "tmp_or_scratch": "review; candidate to clear after explicit operator confirmation (not in daily lane)",
    "lab_or_tatiana": "review; lab or Tatiana — treat as non-production evidence",
    "loose_root_files": "review clutter at report root; prefer timestamped or subfolders over new loose files",
    "large_files": "review; consider compression or out-of-repo storage; verify still needed",
    "unknown": "review and classify; do not delete until purpose is clear",
    "repo_bootstrap": "keep (tracked README / .gitkeep; do not treat as report output)",
}


def by_bucket_aggregation(entries: list[FileEntry]) -> dict[str, dict[str, int | float]]:
    out: dict[str, dict[str, int | float]] = {}
    for e in entries:
        d = out.setdefault(e.primary_bucket, {"file_count": 0, "total_bytes": 0})
        d["file_count"] = int(d["file_count"]) + 1
        d["total_bytes"] = int(d["total_bytes"]) + e.size_bytes
    for k in out:
        out[k]["size_mb"] = round(out[k]["total_bytes"] / (1024 * 1024), 4)
    return dict(sorted(out.items(), key=lambda kv: (-int(kv[1]["total_bytes"]), kv[0])))


def over_threshold_entries(
    entries: list[FileEntry], threshold: int, limit: int
) -> list[FileEntry]:
    return sorted(
        [e for e in entries if e.size_bytes >= threshold],
        key=lambda e: (-e.size_bytes, e.relative_path),
    )[:limit]


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
    action_order = (
        "active_current",
        "active_workspace_misc",
        "client_pack_latest",
        "reference",
        "archive",
        "tmp_or_scratch",
        "lab_or_tatiana",
        "loose_root_files",
        "unknown",
        "repo_bootstrap",
        "large_files",
    )
    for bucket in action_order:
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
    root = _norm(root)
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
