#!/usr/bin/env python3
from __future__ import annotations

"""
Build a pilot input CSV from an existing Tatiana marketing cohort CSV.

Maps common columns (id, subject, body_for_review, ...) to pilot canonical headers.
Does not call any LLM or inbox APIs.
"""

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.tatiana_copilot.loader import load_csv_rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Prepare tatiana_pilot input CSV from cohort export")
    ap.add_argument("--cohort-csv", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument(
        "--case-id-prefix",
        default="pilot",
        help="case_id = {prefix}_{row id or rank} (default: pilot)",
    )
    args = ap.parse_args()

    rows = load_csv_rows(args.cohort_csv)
    rows = rows[: max(0, args.limit)]
    out_rows: list[dict[str, str]] = []

    for i, r in enumerate(rows, start=1):
        rid = (r.get("id") or r.get("review_priority_rank") or str(i)).strip()
        case_id = f"{args.case_id_prefix}_{rid}"
        subj = (r.get("subject") or "").strip()
        body = (r.get("body_for_review") or r.get("body_text") or "").strip()
        if not body:
            continue
        out_rows.append(
            {
                "case_id": case_id,
                "subject": subj,
                "body_text": body,
                "from_email": (r.get("sender_email") or r.get("from_email") or "").strip(),
                "from_name": (r.get("sender_name") or r.get("from_name") or "").strip(),
                "thread_hint": "",
                "received_at": (r.get("date_iso") or "").strip(),
                "case_type": (r.get("human_label") or r.get("auto_label") or "").strip(),
                "notes": (r.get("marketing_rank_notes") or "").strip(),
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "subject",
        "body_text",
        "from_email",
        "from_name",
        "thread_hint",
        "received_at",
        "case_type",
        "notes",
    ]
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in out_rows:
            w.writerow(row)
    print(f"Wrote {len(out_rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
