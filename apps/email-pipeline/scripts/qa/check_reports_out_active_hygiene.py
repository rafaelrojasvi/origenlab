#!/usr/bin/env python3
"""Read-only guardrail: ensure reports/out/active stays focused on current workspace.

Fails when unexpected generated artifacts exist at active root outside the allowed set.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

_ALLOWED_ROOT_FILES = {
    "README.md",
    "CLEANUP_INDEX.md",
    ".gitkeep",
    "all_known_marketing_contacts_dedup.csv",
    "outreach_contacted_all.csv",
    "operational_trust_scorecard.json",
    "operational_stack_last_run.json",
}

_ALLOWED_ROOT_DIRS = {
    "current",
    "operational_run_manifests",
}


def _classify_unexpected(entry: Path) -> str:
    name = entry.name
    if entry.is_dir():
        if name.startswith("archive_send_batch"):
            return "legacy_archive_batch_folder"
        if "deepsearch" in name or "research" in name:
            return "legacy_research_folder"
        if "manual_html" in name:
            return "legacy_manual_html_folder"
        return "unexpected_active_subdir"
    if entry.suffix.lower() in {".csv", ".json", ".txt", ".md"}:
        if "send_ready" in name:
            return "send_artifact_outside_current"
        if name.startswith("overlap_") or name.startswith("gate_"):
            return "audit_artifact_outside_current"
        return "generated_file_outside_current"
    return "unexpected_active_entry"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--active-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active",
        help="Path to reports/out/active (default: repo reports/out/active).",
    )
    ap.add_argument("--json-out", type=Path, default=None, help="Optional JSON report output path.")
    args = ap.parse_args(argv)

    active_dir = Path(args.active_dir)
    if not active_dir.is_dir():
        print(f"error: active directory not found: {active_dir}", file=sys.stderr)
        return 2

    unexpected: list[dict[str, str]] = []
    for entry in sorted(active_dir.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir() and entry.name in _ALLOWED_ROOT_DIRS:
            continue
        if entry.is_file() and entry.name in _ALLOWED_ROOT_FILES:
            continue
        unexpected.append(
            {
                "path": str(entry),
                "name": entry.name,
                "kind": _classify_unexpected(entry),
            }
        )

    payload = {
        "active_dir": str(active_dir),
        "ok": len(unexpected) == 0,
        "unexpected_count": len(unexpected),
        "unexpected": unexpected,
        "recommendation": (
            "Move unexpected entries into reports/out/archive/{campaigns,audits,research,manual_html}/ "
            "or reports/out/reference/, then re-run."
        ),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")

    if unexpected:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
