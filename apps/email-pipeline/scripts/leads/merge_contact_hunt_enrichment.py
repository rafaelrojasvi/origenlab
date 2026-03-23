#!/usr/bin/env python3
"""Merge a Deep Research enrichment CSV into the v1.2 contact-hunt sheet.

Assumptions:
- Both CSVs include `id_lead`.
- Enrichment CSV includes some subset of the contact-hunt columns (names should match).

Default behavior:
- Only fill fields in the base sheet when the base value is empty.
- Does not guess emails/phones.

Cohort drift: if ``leads_contact_hunt_current_merged.csv`` was built from an older id set than
``leads_contact_hunt_current.csv``, re-base merged onto current while keeping overlapping
enrichment by ``id_lead``::

    uv run python scripts/leads/merge_contact_hunt_enrichment.py \\
      -b reports/out/active/leads_contact_hunt_current.csv \\
      -e reports/out/active/leads_contact_hunt_current_merged.csv \\
      -o reports/out/active/leads_contact_hunt_current_merged.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        headers = list(r.fieldnames or [])
        rows = list(r)
    return headers, rows


def _is_empty(v: str | None) -> bool:
    return v is None or str(v).strip() == ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge enrichment CSV into contact-hunt sheet by id_lead.")
    ap.add_argument("--base", "-b", type=Path, required=True, help="Base contact-hunt CSV.")
    ap.add_argument("--enrichment", "-e", type=Path, required=True, help="Enrichment CSV from Deep Research.")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output merged CSV path.")
    ap.add_argument(
        "--overwrite-non-empty",
        action="store_true",
        help="If set, overwrite non-empty cells in the base sheet with enrichment values.",
    )
    args = ap.parse_args()

    base_headers, base_rows = _read_csv(args.base)
    enr_headers, enr_rows = _read_csv(args.enrichment)

    if "id_lead" not in base_headers:
        raise SystemExit("Base CSV must include `id_lead` column.")
    if "id_lead" not in enr_headers:
        raise SystemExit("Enrichment CSV must include `id_lead` column.")

    # Union headers: keep base order, then append any enrichment-only columns.
    merged_headers = list(base_headers)
    for h in enr_headers:
        if h not in merged_headers:
            merged_headers.append(h)

    base_by_id: dict[str, dict[str, str]] = {}
    for r in base_rows:
        rid = (r.get("id_lead") or "").strip()
        if not rid:
            continue
        base_by_id[rid] = r

    updated = 0
    for er in enr_rows:
        rid = (er.get("id_lead") or "").strip()
        if not rid or rid not in base_by_id:
            continue
        br = base_by_id[rid]
        for h in enr_headers:
            if h == "id_lead":
                continue
            if not _is_empty(er.get(h)):
                if args.overwrite_non_empty or _is_empty(br.get(h)):
                    br[h] = er.get(h) or ""
        updated += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=merged_headers)
        w.writeheader()
        w.writerows(base_rows)

    print(f"Merged enrichment into base for {updated} lead rows.")
    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

