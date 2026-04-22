#!/usr/bin/env python3
"""Prepare canonical outbound campaign workspace under reports/out/active/current."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

_CANONICAL_FILES: tuple[str, ...] = (
    "research_queue.csv",
    "reviewed_deepsearch.csv",
    "overlap_audit.csv",
    "gate_audit.csv",
    "send_ready.csv",
    "outbound_summary.json",
    "send_manifest.json",
    "mark_contacted_result.json",
)


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-_")
    return s.lower() or "campaign"


def _archive_dir(archive_root: Path, campaign_slug: str) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = archive_root / f"{day}_{_slugify(campaign_slug)}"
    if not base.exists():
        return base
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    return archive_root / f"{day}_{_slugify(campaign_slug)}_{ts}"


def _clear_directory_contents(target: Path) -> None:
    if not target.exists():
        return
    for p in target.iterdir():
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


def _recommended_steps() -> list[str]:
    return [
        "Export research queue to active/current/research_queue.csv.",
        "Save reviewed DeepSearch output to active/current/reviewed_deepsearch.csv.",
        "Run overlap audit and write active/current/overlap_audit.csv.",
        "Run gate audit and write active/current/gate_audit.csv.",
        "Export send-ready recipients to active/current/send_ready.csv.",
        "After send, store send_manifest.json and mark_contacted_result.json.",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign-slug", required=True, help="Campaign identifier for manifest/archive naming.")
    ap.add_argument("--operator", default="", help="Optional operator name/email.")
    ap.add_argument(
        "--archive-existing",
        action="store_true",
        help="Archive existing active/current contents into reports/out/archive/YYYY-MM-DD_<slug>/.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only; write nothing.")
    ap.add_argument(
        "--reports-out-dir",
        type=Path,
        default=_ROOT / "reports" / "out",
        help="Reports out root (default: <repo>/reports/out).",
    )
    args = ap.parse_args()

    reports_out = Path(args.reports_out_dir).resolve()
    active_current = reports_out / "active" / "current"
    archive_root = reports_out / "archive"

    now_iso = datetime.now(timezone.utc).isoformat()
    current_paths = {
        "research_queue": "reports/out/active/current/research_queue.csv",
        "reviewed_deepsearch": "reports/out/active/current/reviewed_deepsearch.csv",
        "overlap_audit": "reports/out/active/current/overlap_audit.csv",
        "gate_audit": "reports/out/active/current/gate_audit.csv",
        "send_ready": "reports/out/active/current/send_ready.csv",
        "outbound_summary": "reports/out/active/current/outbound_summary.json",
        "send_manifest": "reports/out/active/current/send_manifest.json",
        "mark_contacted_result": "reports/out/active/current/mark_contacted_result.json",
        "campaign_manifest": "reports/out/active/current/campaign_manifest.json",
    }

    manifest = {
        "campaign_slug": str(args.campaign_slug).strip(),
        "created_at": now_iso,
        "operator": str(args.operator or "").strip(),
        "current_paths": current_paths,
        "recommended_next_steps": _recommended_steps(),
        "notes": "Use active/current only for the live campaign; archive old runs before reuse.",
    }

    if args.dry_run:
        print("[dry-run] would ensure directory:", active_current)
        if args.archive_existing:
            print("[dry-run] would archive existing active/current contents to:", _archive_dir(archive_root, args.campaign_slug))
        else:
            print("[dry-run] would clear existing active/current contents in place.")
        for name in _CANONICAL_FILES:
            print("[dry-run] would create/clean:", active_current / name)
        print("[dry-run] would write:", active_current / "campaign_manifest.json")
        return 0

    active_current.mkdir(parents=True, exist_ok=True)

    if args.archive_existing and any(active_current.iterdir()):
        archive_dir = _archive_dir(archive_root, args.campaign_slug)
        archive_dir.mkdir(parents=True, exist_ok=True)
        for p in list(active_current.iterdir()):
            shutil.move(str(p), str(archive_dir / p.name))
        print(f"Archived previous current workspace to {archive_dir}")
    else:
        _clear_directory_contents(active_current)

    for name in _CANONICAL_FILES:
        p = active_current / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")

    manifest_path = active_current / "campaign_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared campaign workspace: {active_current}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

