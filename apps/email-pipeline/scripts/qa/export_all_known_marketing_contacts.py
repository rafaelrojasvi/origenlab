#!/usr/bin/env python3
"""Merge known marketing contact CSVs into one deduplicated file + optional email-only list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.merge_marketing_contact_csvs import (
    default_active_marketing_csv_paths,
    merge_contact_csvs_dedupe_by_email,
    write_merged_contacts_csv,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write all_known_marketing_contacts_dedup.csv (and optional .txt) under reports/out/active."
    )
    ap.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="Output CSV path (default: reports/out/active/all_known_marketing_contacts_dedup.csv)",
    )
    ap.add_argument(
        "--out-emails-txt",
        type=Path,
        default=None,
        help="Optional one-email-per-line file (default: reports/out/reference/all_known_marketing_emails_dedup.txt)",
    )
    ap.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Input CSV paths (default: discovery across active/archive/reference with contacted-all first)",
    )
    args = ap.parse_args(argv)

    reports_active = (_ROOT / "reports" / "out" / "active").resolve()
    inputs = tuple(args.inputs) if args.inputs else default_active_marketing_csv_paths(reports_active=reports_active)
    out_csv = (args.out_csv or (reports_active / "all_known_marketing_contacts_dedup.csv")).expanduser().resolve()
    existing_inputs = tuple(p for p in inputs if p.expanduser().resolve().is_file())

    if not existing_inputs:
        print(
            {
                "inputs": [str(p) for p in inputs],
                "missing_inputs": [str(p) for p in inputs],
                "error": "no_existing_input_csvs_found",
                "out_csv": str(out_csv),
            },
            flush=True,
        )
        return 2

    rows = merge_contact_csvs_dedupe_by_email(existing_inputs)
    if not rows:
        print(
            {
                "inputs": [str(p) for p in inputs],
                "existing_inputs": [str(p) for p in existing_inputs],
                "error": "no_contact_emails_found_in_inputs",
                "out_csv": str(out_csv),
            },
            flush=True,
        )
        return 3
    write_merged_contacts_csv(rows, out_csv)

    emails_txt = args.out_emails_txt
    if emails_txt is None:
        emails_txt = _ROOT / "reports" / "out" / "reference" / "all_known_marketing_emails_dedup.txt"
    if emails_txt is not None:
        emails_txt = emails_txt.expanduser().resolve()
        emails_txt.parent.mkdir(parents=True, exist_ok=True)
        emails_txt.write_text(
            "\n".join(sorted({r["contact_email"].strip().lower() for r in rows if r.get("contact_email")}))
            + "\n",
            encoding="utf-8",
        )

    missing = [str(p) for p in inputs if not p.is_file()]
    print(
        {
            "inputs": [str(p) for p in inputs],
            "existing_inputs": [str(p) for p in existing_inputs],
            "missing_inputs": missing,
            "unique_emails": len(rows),
            "out_csv": str(out_csv),
            "out_emails_txt": str(emails_txt) if emails_txt else None,
        },
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
