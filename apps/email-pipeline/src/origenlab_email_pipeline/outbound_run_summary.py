"""Load and format canonical outbound run metadata from summary JSON (operator trust / debugging).

Supports:
- Archive: ``archive_outreach_build_summary.json`` (nested ``outbound_run``)
- Lead: ``<stem>_outbound_summary.json`` from ``--write-outbound-summary`` (top-level ``outbound_run``)

No I/O in the formatter — easy to unit test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_summary_json(path: Path) -> dict[str, Any]:
    """Parse a UTF-8 JSON object from disk."""
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("summary JSON must be an object at the root")
    return data


def extract_outbound_run(summary: dict[str, Any]) -> dict[str, Any]:
    """Return the ``outbound_run`` object, or the root if it already looks like an envelope."""
    inner = summary.get("outbound_run")
    if isinstance(inner, dict) and inner and (
        "lane" in inner or inner.get("schema_version") is not None
    ):
        return inner
    if summary.get("lane") is not None and summary.get("gmail_user") is not None:
        return summary
    raise KeyError(
        "No outbound_run envelope found (expected key 'outbound_run' or root fields lane + gmail_user)"
    )


def format_outbound_run_trust_report(run: dict[str, Any]) -> str:
    """Human-readable trust lines for operators (stable field order)."""
    lines: list[str] = []
    lane = str(run.get("lane") or "")
    lines.append(f"lane:              {lane}")
    lines.append(f"schema_version:    {run.get('schema_version', '')}")
    lines.append(f"gmail_user:        {run.get('gmail_user', '')}")
    lines.append(f"sqlite_path:       {run.get('sqlite_path', '')}")
    sf = run.get("sent_folders_resolved")
    if isinstance(sf, list):
        lines.append(f"sent_folders:      {', '.join(str(x) for x in sf)}")
    else:
        lines.append(f"sent_folders:      {sf!s}")
    lines.append(f"sent_defaults:     {run.get('sent_folder_defaults_used', '')}")
    lines.append(f"strict_graph_noise:{run.get('strict_contact_graph_noise', '')}")
    lines.append(f"created_at_utc:    {run.get('created_at_utc', '')}")
    counts = run.get("counts")
    if isinstance(counts, dict) and counts:
        lines.append("counts:")
        for k in sorted(counts.keys()):
            lines.append(f"  {k}: {counts[k]}")
    paths = run.get("artifact_paths")
    if isinstance(paths, dict) and paths:
        lines.append("artifact_paths:")
        for k in sorted(paths.keys()):
            lines.append(f"  {k}: {paths[k]}")
    return "\n".join(lines) + "\n"


def trust_report_from_summary_path(path: Path) -> str:
    """Load JSON from *path* and return formatted trust report."""
    summary = load_summary_json(path)
    run = extract_outbound_run(summary)
    return format_outbound_run_trust_report(run)
