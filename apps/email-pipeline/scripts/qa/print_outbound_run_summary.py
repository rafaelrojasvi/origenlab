#!/usr/bin/env python3
"""Print key trust fields from a canonical outbound summary JSON (archive or lead).

Reads ``outbound_run`` from:
- ``archive_outreach_build_summary.json`` (full batch summary)
- ``*_outbound_summary.json`` (lead lane with ``--write-outbound-summary``)

Example::

  uv run python scripts/qa/print_outbound_run_summary.py \\
    --json reports/out/active/archive_send_batch/archive_outreach_build_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.outbound_run_summary import (  # noqa: E402
    trust_report_from_summary_path,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--json",
        type=Path,
        required=True,
        help="Path to archive_outreach_build_summary.json or lead *_outbound_summary.json",
    )
    args = p.parse_args()
    path = args.json.expanduser()
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(trust_report_from_summary_path(path))
    except (KeyError, ValueError, json.JSONDecodeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
