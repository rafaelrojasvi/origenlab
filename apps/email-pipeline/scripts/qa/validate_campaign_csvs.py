#!/usr/bin/env python3
"""Validate campaign CSV contracts under reports/out/active/current."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.csv_contracts import (
    detect_trailing_prose_or_summary_lines,
    extract_email_from_aliases,
    has_required_columns,
    normalize_confidence,
    read_csv_normalized,
    sanitize_csv_text,
    source_host_matches_domain,
    source_is_official_registry_exception,
    source_looks_third_party,
    validate_confidence,
    validate_email_syntax,
    validate_source_url,
)


KIND_REQUIRED = {
    "research_queue": ("lead_id", "organization_name", "fit_bucket", "research_query_1"),
    "reviewed_deepsearch": (
        "lead_id",
        "org_name",
        "resolved_domain",
        "resolved_contact_email",
        "resolved_contact_name",
        "contact_source_url",
        "source_type",
        "confidence",
        "notes",
    ),
    "marketing_contacts": (
        "institution_name",
        "region",
        "city",
        "type",
        "contact_email",
        "contact_label",
        "source_url",
        "confidence",
    ),
    "gate_audit": (
        "email",
        "lead_id",
        "final_eligible",
        "exclusion_reason",
        "blocked_by_sent",
        "blocked_by_outreach_state",
        "blocked_by_email_suppression",
        "blocked_by_domain_suppression",
    ),
    "send_ready": ("contact_email", "institution_name", "email_source"),
}


class ValidationResult(dict):
    pass


def _kind_from_path(path: Path) -> str:
    n = path.name.lower()
    if "research_queue" in n:
        return "research_queue"
    if "reviewed_deepsearch" in n:
        return "reviewed_deepsearch"
    if "gate_audit" in n:
        return "gate_audit"
    if "send_ready" in n:
        return "send_ready"
    if "marketing" in n:
        return "marketing_contacts"
    return "unknown"


def _validate_bool01(v: str) -> bool:
    return str(v or "").strip() in {"0", "1"}


def _validate_file(path: Path, kind: str) -> ValidationResult:
    warns = detect_trailing_prose_or_summary_lines(path)
    if not path.is_file():
        return ValidationResult(
            file=str(path),
            kind=kind,
            rows=0,
            valid_rows=0,
            invalid_rows=0,
            warnings=warns,
            errors=[f"missing file: {path}"],
        )
    headers, rows = read_csv_normalized(path)
    errors: list[str] = []
    warnings: list[str] = list(warns)
    valid = 0
    invalid = 0
    if kind in KIND_REQUIRED:
        ok, miss = has_required_columns(headers, KIND_REQUIRED[kind])
        if not ok:
            errors.append(f"missing required columns: {', '.join(miss)}")
    if kind == "send_ready" and ("id_lead" not in headers and "case_id" not in headers):
        errors.append("send_ready requires id_lead or case_id")
    dup_counter: dict[str, int] = {}

    for i, r in enumerate(rows, start=2):
        row_err = False
        if kind == "reviewed_deepsearch":
            lid = str(r.get("lead_id") or "").strip()
            if not lid.isdigit():
                errors.append(f"line {i}: lead_id must be integer-like")
                row_err = True
            conf = normalize_confidence(r.get("confidence", ""))
            if not validate_confidence(conf):
                errors.append(f"line {i}: invalid confidence={conf!r}")
                row_err = True
            em = validate_email_syntax(r.get("resolved_contact_email", ""))
            if (r.get("resolved_contact_email") or "").strip() and not em:
                errors.append(f"line {i}: invalid resolved_contact_email")
                row_err = True
            if em:
                dup_counter[em] = dup_counter.get(em, 0) + 1
            src = str(r.get("contact_source_url") or "").strip()
            dom = str(r.get("resolved_domain") or "").strip().lower()
            if em and not src:
                warnings.append(f"line {i}: email present without contact_source_url")
            if src and not validate_source_url(src):
                errors.append(f"line {i}: invalid contact_source_url")
                row_err = True
            if conf == "high" and em:
                if not src:
                    errors.append(f"line {i}: high confidence requires contact_source_url")
                    row_err = True
                elif not (
                    source_host_matches_domain(src, dom)
                    or source_is_official_registry_exception(src)
                ):
                    msg = "high confidence source host does not match resolved_domain"
                    if source_looks_third_party(src):
                        errors.append(f"line {i}: {msg} (third-party-like source)")
                        row_err = True
                    else:
                        warnings.append(f"line {i}: {msg}")
        elif kind == "marketing_contacts":
            em = validate_email_syntax(extract_email_from_aliases(r, ("contact_email",)))
            if not em:
                errors.append(f"line {i}: invalid contact_email")
                row_err = True
            conf = normalize_confidence(r.get("confidence", ""))
            if not validate_confidence(conf):
                errors.append(f"line {i}: invalid confidence")
                row_err = True
        elif kind == "gate_audit":
            fe = str(r.get("final_eligible") or "")
            ex = str(r.get("exclusion_reason") or "").strip()
            if not _validate_bool01(fe):
                errors.append(f"line {i}: final_eligible must be 0/1")
                row_err = True
            for k in (
                "blocked_by_sent",
                "blocked_by_outreach_state",
                "blocked_by_email_suppression",
                "blocked_by_domain_suppression",
            ):
                if not _validate_bool01(r.get(k, "")):
                    errors.append(f"line {i}: {k} must be 0/1")
                    row_err = True
            if fe == "1" and ex:
                errors.append(f"line {i}: final_eligible=1 requires blank exclusion_reason")
                row_err = True
            if ex == "invalid_email" and str(r.get("blocked_by_invalid_email") or "") != "1":
                errors.append(f"line {i}: invalid_email exclusion requires blocked_by_invalid_email=1")
                row_err = True
        elif kind == "send_ready":
            em = validate_email_syntax(r.get("contact_email", ""))
            if not em:
                errors.append(f"line {i}: invalid contact_email")
                row_err = True
            else:
                dup_counter[em] = dup_counter.get(em, 0) + 1
            for val in r.values():
                sv = str(val or "")
                if sanitize_csv_text(sv) != sv.strip():
                    warnings.append(f"line {i}: control/whitespace-normalized field detected")
                    break
        elif kind == "research_queue":
            lid = str(r.get("lead_id") or "").strip()
            if not lid.isdigit():
                errors.append(f"line {i}: lead_id must be integer-like")
                row_err = True
        if row_err:
            invalid += 1
        else:
            valid += 1

    if kind == "reviewed_deepsearch":
        for em, n in sorted(dup_counter.items()):
            if n > 1:
                warnings.append(f"duplicate email: {em} ({n} rows)")
    if kind == "send_ready":
        for em, n in sorted(dup_counter.items()):
            if n > 1:
                errors.append(f"duplicate contact_email: {em} ({n} rows)")
    return ValidationResult(
        file=str(path),
        kind=kind,
        rows=len(rows),
        valid_rows=valid,
        invalid_rows=invalid,
        warnings=warnings,
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, default=Path("reports/out/active/current"))
    ap.add_argument("--file", action="append", type=Path, default=[])
    ap.add_argument(
        "--kind",
        choices=("reviewed_deepsearch", "research_queue", "marketing_contacts", "gate_audit", "send_ready"),
        default=None,
    )
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    targets: list[tuple[Path, str]] = []
    if args.file:
        for f in args.file:
            targets.append((Path(f), args.kind or _kind_from_path(Path(f))))
    else:
        w = Path(args.workspace)
        targets = [
            (w / "research_queue.csv", "research_queue"),
            (w / "reviewed_deepsearch.csv", "reviewed_deepsearch"),
            (w / "overlap_audit.csv", "unknown"),
            (w / "gate_audit.csv", "gate_audit"),
            (w / "send_ready.csv", "send_ready"),
        ]

    results = [_validate_file(p, k) for p, k in targets]
    payload = {"results": [dict(r) for r in results]}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        print(
            f"{r['file']} kind={r['kind']} rows={r['rows']} valid={r['valid_rows']} invalid={r['invalid_rows']} "
            f"warnings={len(r['warnings'])} errors={len(r['errors'])}"
        )
        for w in r["warnings"][:10]:
            print(f"  warn: {w}")
        for e in r["errors"][:10]:
            print(f"  error: {e}")
    any_errors = any(r["errors"] for r in results)
    if args.strict and any_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

