#!/usr/bin/env python3
"""Static evidence audit for research candidate CSV outputs.

Checks lightweight evidence quality signals without web crawling:
- homepage-only source_url (weak evidence)
- generic contact + homepage
- email/source domain mismatch
- non-specific source page path
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


GENERIC_LOCAL_PARTS = {
    "contacto",
    "contact",
    "info",
    "admision",
    "admisiones",
    "comunicaciones",
    "extension",
    "prensa",
}
WEAK_PATHS = {"", "/", "/index", "/home", "/inicio"}


def _domain(email: str) -> str:
    e = str(email or "").strip().lower()
    return e.split("@", 1)[1] if "@" in e else ""


def _local(email: str) -> str:
    e = str(email or "").strip().lower()
    return e.split("@", 1)[0] if "@" in e else ""


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "").strip()).hostname or "").lower()
    except Exception:
        return ""


def _path(url: str) -> str:
    try:
        return (urlparse(str(url or "").strip()).path or "").strip().lower()
    except Exception:
        return ""


def _specific_path(url: str) -> bool:
    p = _path(url)
    if p in WEAK_PATHS:
        return False
    if p.endswith(".pdf"):
        return True
    return len(p.strip("/")) > 1


def _token_overlap(a: str, b: str) -> bool:
    ta = {x for x in a.replace("-", ".").split(".") if len(x) >= 4}
    tb = {x for x in b.replace("-", ".").split(".") if len(x) >= 4}
    return bool(ta & tb)


def audit_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=2):
        email = str(row.get("contact_email") or "").strip().lower()
        source = str(row.get("source_url") or "").strip()
        reasons: list[str] = []
        em_domain = _domain(email)
        src_host = _host(source)
        p = _path(source)
        is_homepage = p in WEAK_PATHS
        is_specific = _specific_path(source)
        local = _local(email)
        if is_homepage:
            reasons.append("homepage_source_weak_evidence")
        if is_homepage and local in GENERIC_LOCAL_PARTS:
            reasons.append("generic_contact_homepage_weak")
        if src_host and em_domain and not _token_overlap(src_host, em_domain):
            reasons.append("email_domain_source_mismatch")
        if not is_specific:
            reasons.append("source_page_not_specific")
        if reasons:
            out.append(
                {
                    "source_line": str(idx),
                    "institution_name": str(row.get("institution_name") or ""),
                    "contact_email": email,
                    "source_url": source,
                    "evidence_warning": ";".join(dict.fromkeys(reasons)),
                }
            )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="Candidate CSV path to audit.")
    ap.add_argument("--out-csv", type=Path, default=None, help="Optional warning CSV path.")
    ap.add_argument("--out-json", type=Path, default=None, help="Optional warning JSON path.")
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"Input CSV not found: {args.input}", file=sys.stderr)
        return 2
    with args.input.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(f)]
    warnings = audit_rows(rows)

    out_csv = args.out_csv
    out_json = args.out_json
    if out_csv is not None:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            fieldnames = [
                "source_line",
                "institution_name",
                "contact_email",
                "source_url",
                "evidence_warning",
            ]
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            w.writeheader()
            for row in warnings:
                w.writerow(row)
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {"input": str(args.input), "warning_count": len(warnings), "warnings": warnings}
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "input_rows": len(rows),
                "warning_rows": len(warnings),
                "ok": len(warnings) == 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

