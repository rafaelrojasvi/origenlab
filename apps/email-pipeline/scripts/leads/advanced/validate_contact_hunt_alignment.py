#!/usr/bin/env python3
"""Verify that contact-hunt current and merged CSVs share the same id_lead population.

Use before `import_contact_hunt_to_sqlite.py` when the merged sheet must correspond
to a specific hunt export.

Exit code 0 = aligned; 1 = misaligned or invalid inputs; 2 = missing files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.hunt_csv_alignment import describe_hunt_misalignment


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate id_lead set equality between hunt current and merged CSVs."
    )
    ap.add_argument(
        "--current",
        "-c",
        type=Path,
        default=Path("reports/out/active/leads_contact_hunt_current.csv"),
        help="Base hunt CSV (default: reports/out/active/leads_contact_hunt_current.csv)",
    )
    ap.add_argument(
        "--merged",
        "-m",
        type=Path,
        default=Path("reports/out/active/leads_contact_hunt_current_merged.csv"),
        help="Merged hunt CSV (default: reports/out/active/leads_contact_hunt_current_merged.csv)",
    )
    args = ap.parse_args()

    current = args.current.resolve()
    merged = args.merged.resolve()
    if not current.is_file():
        print(f"ERROR: current hunt CSV not found: {current}", file=sys.stderr)
        return 2
    if not merged.is_file():
        print(f"ERROR: merged hunt CSV not found: {merged}", file=sys.stderr)
        return 2

    try:
        msg = describe_hunt_misalignment(current, merged)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if msg:
        print(msg, file=sys.stderr)
        return 1

    print(f"OK: id_lead populations match ({current.name} ↔ {merged.name}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
