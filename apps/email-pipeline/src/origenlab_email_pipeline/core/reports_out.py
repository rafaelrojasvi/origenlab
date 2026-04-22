"""Shared read-only logic for `reports/out` tree classification and planning.

Used by ``plan_reports_out_cleanup`` and ``archive_reports_out_generated`` so bucket
names and path rules have a single definition. This module does **not** print, parse
CLI, move, or delete files. ``scan_reports_out`` only reads the filesystem to stat files.

See :mod:`scripts.qa.plan_reports_out_cleanup` and :mod:`scripts.tools.archive_reports_out_generated`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FULL_RUN_PREFIX = re.compile(r"^full_\d{8}_\d{6}$", re.IGNORECASE)


def normalize_reports_out_root(p: Path) -> Path:
    return p.resolve()


@dataclass(frozen=True, slots=True)
class FileEntry:
    relative_path: str
    size_bytes: int
    primary_bucket: str
    is_over_large_threshold: bool


def is_protected_artifact_basename(name: str) -> bool:
    n = str(name).casefold()
    return n in (".gitkeep", "readme.md", ".gitignore")


def is_excluded_root_artifact(name: str) -> bool:
    """Single path segment: README / .gitkeep at repository bootstrap (planner)."""
    return is_protected_artifact_basename(name)


def path_has_protected_artifact_basename(rel: Path) -> bool:
    """True if any path component is README / .gitkeep / .gitignore (archiver guard)."""
    return any(is_protected_artifact_basename(n) for n in rel.parts)


def is_under_manual_cleanup(rel: Path) -> bool:
    parts = [p.casefold() for p in rel.parts]
    if len(parts) < 2:
        return False
    return parts[0] == "archive" and parts[1] == "manual_cleanup"


def is_under_top_level_active(rel: Path) -> bool:
    """True if path is under top-level ``active/`` (campaign workspace root)."""
    return len(rel.parts) >= 1 and rel.parts[0].casefold() == "active"


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
    root = normalize_reports_out_root(root)
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

PROPOSED_ACTION_PRINT_ORDER: tuple[str, ...] = (
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


def by_bucket_aggregation(entries: list[FileEntry]) -> dict[str, dict[str, int | float]]:
    out: dict[str, dict[str, int | float]] = {}
    for e in entries:
        d = out.setdefault(e.primary_bucket, {"file_count": 0, "total_bytes": 0})
        d["file_count"] = int(d["file_count"]) + 1
        d["total_bytes"] = int(d["total_bytes"]) + e.size_bytes
    for k in out:
        out[k]["size_mb"] = round(int(out[k]["total_bytes"]) / (1024 * 1024), 4)
    return dict(sorted(out.items(), key=lambda kv: (-int(kv[1]["total_bytes"]), kv[0])))


def over_threshold_entries(
    entries: list[FileEntry], threshold: int, limit: int
) -> list[FileEntry]:
    return sorted(
        [e for e in entries if e.size_bytes >= threshold],
        key=lambda e: (-e.size_bytes, e.relative_path),
    )[:limit]


def bucket_eligible_for_move(
    bucket: str,
    *,
    include_tmp: bool,
    include_lab: bool,
    include_loose_root: bool,
    include_unknown: bool,
    allow_active_current: bool,
    allow_reference: bool,
) -> bool:
    """Select buckets for the manual_cleanup archiver (matches CLI flags, no ``argparse``)."""
    if bucket in ("active_current", "reference"):
        if bucket == "active_current" and allow_active_current:
            return True
        if bucket == "reference" and allow_reference:
            return True
        return False
    m: dict[str, bool] = {
        "tmp_or_scratch": include_tmp,
        "lab_or_tatiana": include_lab,
        "loose_root_files": include_loose_root,
        "unknown": include_unknown,
    }
    if bucket not in m:
        return False
    return bool(m[bucket])
