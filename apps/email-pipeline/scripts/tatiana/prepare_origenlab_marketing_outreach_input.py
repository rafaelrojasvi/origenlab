#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_TYPES,
    build_marketing_outreach_seed_body,
)


def _load_rows(path: Path) -> list[dict[str, str]]:
    suf = path.suffix.lower()
    if suf == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            return [{str(k): "" if v is None else str(v) for k, v in row.items()} for row in csv.DictReader(f)]
    if suf == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("rows") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise ValueError("JSON input must be a list of rows or {'rows': [...]} ")
        out: list[dict[str, str]] = []
        for row in items:
            if not isinstance(row, dict):
                raise ValueError("Every JSON row must be an object")
            out.append({str(k): "" if v is None else str(v) for k, v in row.items()})
        return out
    raise ValueError(f"Unsupported input type: {path} (use .csv or .json)")


def _pick(row: dict[str, str], *names: str) -> str:
    lowered = {str(k).strip().lower(): str(v) for k, v in row.items()}
    for n in names:
        if n.lower() in lowered and lowered[n.lower()].strip():
            return lowered[n.lower()].strip()
    return ""


def _case_id(row: dict[str, str], idx: int) -> str:
    return _pick(row, "case_id", "id") or f"marketing_outreach_{idx:03d}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Prepare OrigenLab marketing outreach pilot input from a simple recipient CSV/JSON. "
            "Output is a standard pilot CSV for run_tatiana_pilot_batch.py --origenlab."
        )
    )
    ap.add_argument("--input", type=Path, required=True, help="Simple recipient file (.csv or .json)")
    ap.add_argument("--out", type=Path, required=True, help="Output pilot CSV")
    args = ap.parse_args()

    rows = _load_rows(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "subject",
        "body_text",
        "case_type",
        "recipient_name",
        "institution_name",
        "sector",
        "product_focus",
        "use_case",
        "variant_type",
        "contact_email",
        "custom_note",
        "notes_for_reviewer",
    ]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, row in enumerate(rows, start=1):
            recipient_name = _pick(row, "recipient_name", "recipient")
            institution_name = _pick(row, "institution_name", "institution", "organization_name", "org_name")
            sector = _pick(row, "sector", "segment")
            product_focus = _pick(row, "product_focus", "product_family", "product_line")
            use_case = _pick(row, "use_case", "application")
            variant_type = _pick(row, "variant_type", "variant", "marketing_variant") or MARKETING_VARIANT_GENERAL
            if variant_type not in MARKETING_VARIANT_TYPES:
                variant_type = MARKETING_VARIANT_GENERAL
            contact_email = _pick(row, "contact_email", "recipient_email")
            custom_note = _pick(row, "custom_note", "note", "personalization_note")
            subject = _pick(row, "subject")
            if not subject:
                subject = f"Presentacion OrigenLab | {institution_name}" if institution_name else "Presentacion OrigenLab"
            w.writerow(
                {
                    "case_id": _case_id(row, i),
                    "subject": subject,
                    "body_text": build_marketing_outreach_seed_body(
                        variant_type=variant_type,
                        recipient_name=recipient_name or None,
                        institution_name=institution_name or None,
                        sector=sector or None,
                        product_focus=product_focus or None,
                        use_case=use_case or None,
                        custom_note=custom_note or None,
                    ),
                    "case_type": "marketing_outreach",
                    "recipient_name": recipient_name,
                    "institution_name": institution_name,
                    "sector": sector,
                    "product_focus": product_focus,
                    "use_case": use_case,
                    "variant_type": variant_type,
                    "contact_email": contact_email,
                    "custom_note": custom_note,
                    "notes_for_reviewer": _pick(row, "notes_for_reviewer", "reviewer_notes"),
                }
            )
    print(args.out)


if __name__ == "__main__":
    main()
