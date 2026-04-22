#!/usr/bin/env python3
"""Approve selected manual-review DeepSearch rows for import."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.csv_contracts import normalize_row_dict

_REVIEWED_SCHEMA: list[str] = [
    "lead_id",
    "org_name",
    "resolved_domain",
    "resolved_contact_email",
    "resolved_contact_name",
    "contact_source_url",
    "source_type",
    "confidence",
    "notes",
]


def _load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [normalize_row_dict(dict(r)) for r in reader]
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
    return rows, headers


def _strict_validate_reviewed_csv(path: Path, *, cwd: Path) -> tuple[int, str]:
    validator = cwd / "scripts" / "qa" / "validate_campaign_csvs.py"
    run = subprocess.run(
        [
            sys.executable,
            str(validator),
            "--file",
            str(path),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return run.returncode, (run.stdout + run.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=Path,
        default=Path("reports/out/active/current/reviewed_needs_manual_review.csv"),
        help="Input CSV path (manual-review rows).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("reports/out/active/current/reviewed_manual_approved_to_import.csv"),
        help="Output CSV path with approved rows.",
    )
    ap.add_argument("--approve-lead-id", action="append", default=[], help="Lead ID to approve (repeatable).")
    ap.add_argument("--approve-email", action="append", default=[], help="Email to approve (repeatable).")
    ap.add_argument("--notes", default="", help="Optional note appended to approved rows.")
    ap.add_argument("--operator", default="", help="Optional operator marker appended to approved rows.")
    ap.add_argument("--dry-run", action="store_true", help="Print decisions only; write nothing.")
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1
    if not args.approve_lead_id and not args.approve_email:
        print("Provide at least one --approve-lead-id and/or --approve-email.", file=sys.stderr)
        return 2

    rows, _headers = _load_rows(args.input)
    if not rows:
        print("Input has no rows to approve.", file=sys.stderr)
        return 2

    ids = {str(x).strip() for x in args.approve_lead_id if str(x).strip()}
    emails = {
        normalize_export_email(str(x).strip()) or str(x).strip().lower()
        for x in args.approve_email
        if str(x).strip()
    }
    emails = {e for e in emails if e}

    existing_ids = {str(r.get("lead_id") or "").strip() for r in rows}
    unknown_ids = sorted(i for i in ids if i not in existing_ids)
    if unknown_ids:
        print(f"Unknown approved lead_id(s): {', '.join(unknown_ids)}", file=sys.stderr)
        return 2

    approved: list[dict[str, str]] = []
    skipped = 0
    for r in rows:
        lid = str(r.get("lead_id") or "").strip()
        em = normalize_export_email(str(r.get("resolved_contact_email") or "").strip()) or ""
        hit = (lid in ids) or (em and em in emails)
        if not hit:
            skipped += 1
            continue
        row = {k: str(r.get(k) or "").strip() for k in _REVIEWED_SCHEMA}
        notes_parts: list[str] = []
        if row["notes"]:
            notes_parts.append(row["notes"])
        if args.notes.strip():
            notes_parts.append(f"approval_note={args.notes.strip()}")
        if args.operator.strip():
            notes_parts.append(f"approved_by={args.operator.strip()}")
        if notes_parts:
            row["notes"] = " | ".join(notes_parts)
        approved.append(row)

    if not approved:
        print("No approved rows matched provided lead_id/email filters.", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[dry-run] approved_rows={len(approved)} skipped_rows={skipped} out={args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_REVIEWED_SCHEMA)
        w.writeheader()
        for r in approved:
            w.writerow(r)

    rc, out = _strict_validate_reviewed_csv(args.out, cwd=_ROOT)
    if rc != 0:
        print("Output failed strict reviewed_deepsearch validation.", file=sys.stderr)
        if out:
            print(out, file=sys.stderr)
        return 1

    print(f"approved_rows={len(approved)} skipped_rows={skipped}")
    print(f"output={args.out}")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

