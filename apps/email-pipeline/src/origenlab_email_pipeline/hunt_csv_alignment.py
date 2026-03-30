"""Contact-hunt CSV ``id_lead`` set alignment (current vs merged exports).

Used by QA (e.g. operational trust), merge tooling, and operators validating that enriched hunt
CSVs cover the same lead cohort as the base file."""

from __future__ import annotations

import csv
from pathlib import Path


def id_lead_set_from_hunt_csv(path: Path) -> set[int]:
    """Return the set of integer id_lead values present in a UTF-8-SIG hunt CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "id_lead" not in reader.fieldnames:
            raise ValueError(f"{path}: CSV must include an id_lead column (got {reader.fieldnames!r})")
        out: set[int] = set()
        for row in reader:
            raw = (row.get("id_lead") or "").strip()
            if not raw:
                continue
            try:
                out.add(int(raw))
            except ValueError as e:
                raise ValueError(f"{path}: invalid id_lead {raw!r}") from e
    return out


def describe_hunt_misalignment(current: Path, merged: Path) -> str | None:
    """Return an error message if populations differ; otherwise None."""
    a = id_lead_set_from_hunt_csv(current)
    b = id_lead_set_from_hunt_csv(merged)
    if a == b:
        return None
    only_current = sorted(a - b)
    only_merged = sorted(b - a)
    lines = [
        "Contact-hunt CSV id_lead populations do not match.",
        f"  current: {current} ({len(a)} ids)",
        f"  merged:  {merged} ({len(b)} ids)",
    ]
    if only_current:
        sample = only_current[:20]
        more = f" (+{len(only_current) - 20} more)" if len(only_current) > 20 else ""
        lines.append(f"  Only in current (not in merged): {sample}{more}")
    if only_merged:
        sample = only_merged[:20]
        more = f" (+{len(only_merged) - 20} more)" if len(only_merged) > 20 else ""
        lines.append(f"  Only in merged (not in current): {sample}{more}")
    lines.append(
        "Regenerate the merged file from the current hunt export, or re-export current "
        "from the same lead set before import."
    )
    return "\n".join(lines)
