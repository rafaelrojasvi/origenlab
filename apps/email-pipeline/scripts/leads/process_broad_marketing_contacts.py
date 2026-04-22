#!/usr/bin/env python3
"""Process reviewed broad marketing contacts (DeepSearch volume lane).

Validates ``reviewed_marketing_contacts.csv``, dedupes, and splits against SQLite gate context
and ``do_not_repeat_master.csv``. Does not send mail or import into lead_contact_research.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.candidate_export_gate import evaluate_export_eligibility
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.csv_contracts import (
    extract_email_from_aliases,
    has_required_columns,
    normalize_confidence,
    read_csv_normalized,
    sanitize_csv_text,
    source_is_official_registry_exception,
    source_looks_third_party,
    validate_confidence,
    validate_email_syntax,
    validate_source_url,
)
from origenlab_email_pipeline.outbound_core import (
    gate_context_for_lead_master_export,
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)

_REQUIRED = (
    "institution_name",
    "region",
    "city",
    "type",
    "contact_email",
    "contact_label",
    "source_url",
    "confidence",
)

_SEND_READY_FIELDS = (
    "case_id",
    "contact_email",
    "email_source",
    "institution_name",
    "region",
    "city",
    "type",
    "contact_label",
    "source_url",
    "confidence",
    "fit_signal",
    "variant_type",
)

_GENERIC_LABELS = frozenset(
    {
        "",
        "contact",
        "contacto",
        "email",
        "general",
        "n/a",
        "na",
        "s/a",
        "info",
        "informacion",
        "información",
        "solicitud",
        "admin",
    }
)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _load_master_norms(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            em = str(row.get("email_norm") or row.get("email") or "").strip().lower()
            if em:
                out.add(em)
    return out


def _row_schema_errors(row: dict[str, str], *, line: int) -> list[str]:
    err: list[str] = []
    em = validate_email_syntax(extract_email_from_aliases(row, ("contact_email",)))
    if not em:
        err.append("invalid_email")
    conf = normalize_confidence(row.get("confidence", ""))
    if not validate_confidence(conf) or conf not in {"high", "medium", "low"}:
        err.append("invalid_confidence")
    src = str(row.get("source_url") or "").strip()
    if not src:
        err.append("missing_source_url")
    elif not validate_source_url(src):
        err.append("invalid_source_url")
    fs = str(row.get("fit_signal") or "").strip()
    if fs and len(fs) > 2000:
        err.append("fit_signal_too_long")
    return err


def _generic_label(label: str) -> bool:
    return str(label or "").strip().lower() in _GENERIC_LABELS


def _weak_fit(fit_signal: str) -> bool:
    return len(str(fit_signal or "").strip()) < 4


def _out_row(base: dict[str, str], **extra: str) -> dict[str, str]:
    o = dict(base)
    for k, v in extra.items():
        o[k] = v
    return o


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--workspace",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
    )
    ap.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Defaults to <workspace>/reviewed_marketing_contacts.csv",
    )
    ap.add_argument(
        "--master",
        type=Path,
        default=None,
        help="Defaults to <workspace>/do_not_repeat_master.csv",
    )
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument(
        "--variant-type",
        default="broad_marketing",
        help="Written to send_ready_marketing.variant_type",
    )
    args = ap.parse_args(argv)

    workspace = Path(args.workspace)
    inp = Path(args.input) if args.input else workspace / "reviewed_marketing_contacts.csv"
    master_path = Path(args.master) if args.master else workspace / "do_not_repeat_master.csv"

    if not inp.is_file():
        print(f"Input not found: {inp}", file=sys.stderr)
        return 1

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    workspace.mkdir(parents=True, exist_ok=True)
    out_safe = workspace / "marketing_safe_to_send.csv"
    out_blocked = workspace / "marketing_blocked_already_known.csv"
    out_review = workspace / "marketing_needs_manual_review.csv"
    out_send = workspace / "send_ready_marketing.csv"
    out_summary = workspace / "marketing_contacts_summary.json"

    headers, rows = read_csv_normalized(inp)
    ok, missing = has_required_columns(headers, _REQUIRED)
    if not ok:
        print(f"Missing required columns: {', '.join(missing)}", file=sys.stderr)
        return 2

    master_set = _load_master_norms(master_path)

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    conn = _connect_readonly(db_path)
    try:
        ctx = gate_context_for_lead_master_export(
            conn, gmail_user=gmail_user, sent_folders=sent_folders
        )
    finally:
        conn.close()

    safe_rows: list[dict[str, str]] = []
    blocked_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []

    seen_batch: dict[str, int] = {}
    case_seq = 0

    for i, raw in enumerate(rows, start=2):
        base = {k: sanitize_csv_text(raw.get(k, "")) for k in raw.keys()}
        line_errors = _row_schema_errors(raw, line=i)
        em = validate_email_syntax(extract_email_from_aliases(raw, ("contact_email",)))
        inst = str(raw.get("institution_name") or "").strip()

        if line_errors:
            blocked_rows.append(
                _out_row(base, block_reason=";".join(line_errors), source_line=str(i))
            )
            continue

        assert em is not None
        if em in seen_batch:
            blocked_rows.append(
                _out_row(
                    base,
                    block_reason="duplicate_input",
                    source_line=str(i),
                    duplicate_of_line=str(seen_batch[em]),
                )
            )
            continue
        seen_batch[em] = i

        if em in master_set:
            blocked_rows.append(
                _out_row(base, block_reason="do_not_repeat_master", source_line=str(i))
            )
            continue

        gate = evaluate_export_eligibility(contact_email=em, institution_name=inst, ctx=ctx)
        if not gate.eligible:
            blocked_rows.append(
                _out_row(
                    base,
                    block_reason=";".join(gate.reasons),
                    source_line=str(i),
                )
            )
            continue

        src = str(raw.get("source_url") or "").strip()
        conf = normalize_confidence(raw.get("confidence", ""))
        review_reasons: list[str] = []
        if conf == "low":
            review_reasons.append("low_confidence")
        if source_looks_third_party(src) and not source_is_official_registry_exception(src):
            review_reasons.append("third_party_source")
        if _generic_label(str(raw.get("contact_label") or "")) and _weak_fit(
            str(raw.get("fit_signal") or "")
        ):
            review_reasons.append("generic_label_weak_fit")

        extra = {"source_line": str(i)}
        if review_reasons:
            review_rows.append(
                _out_row(base, review_reason=";".join(review_reasons), **extra)
            )
        else:
            case_seq += 1
            case_id = f"MKT-{case_seq:05d}"
            safe_rows.append(_out_row(base, case_id=case_id, **extra))

    def _write(path: Path, data: list[dict[str, str]], fieldnames: list[str]) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for r in data:
                w.writerow(r)

    safe_fields = list(dict.fromkeys(list(_REQUIRED) + ["fit_signal", "case_id", "source_line"]))
    blocked_fields = list(
        dict.fromkeys(list(_REQUIRED) + ["fit_signal", "block_reason", "source_line", "duplicate_of_line"])
    )
    review_fields = list(
        dict.fromkeys(list(_REQUIRED) + ["fit_signal", "review_reason", "source_line"])
    )

    _write(out_safe, safe_rows, safe_fields)
    _write(out_blocked, blocked_rows, blocked_fields)
    _write(out_review, review_rows, review_fields)

    send_payload: list[dict[str, str]] = []
    for r in safe_rows:
        send_payload.append(
            {
                "case_id": r["case_id"],
                "contact_email": validate_email_syntax(
                    extract_email_from_aliases(r, ("contact_email",))
                )
                or "",
                "email_source": "marketing_contacts",
                "institution_name": r.get("institution_name", ""),
                "region": r.get("region", ""),
                "city": r.get("city", ""),
                "type": r.get("type", ""),
                "contact_label": r.get("contact_label", ""),
                "source_url": r.get("source_url", ""),
                "confidence": r.get("confidence", ""),
                "fit_signal": r.get("fit_signal", ""),
                "variant_type": args.variant_type,
            }
        )
    _write(out_send, send_payload, list(_SEND_READY_FIELDS))

    summary: dict[str, Any] = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "db_path": str(db_path.resolve()),
        "workspace": str(workspace.resolve()),
        "input": str(inp.resolve()),
        "master_path": str(master_path.resolve()),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
        "counts": {
            "input_rows": len(rows),
            "safe_to_send": len(safe_rows),
            "blocked": len(blocked_rows),
            "needs_manual_review": len(review_rows),
            "send_ready_marketing": len(send_payload),
        },
        "outputs": {
            "marketing_safe_to_send": str(out_safe.resolve()),
            "marketing_blocked_already_known": str(out_blocked.resolve()),
            "marketing_needs_manual_review": str(out_review.resolve()),
            "send_ready_marketing": str(out_send.resolve()),
            "marketing_contacts_summary": str(out_summary.resolve()),
        },
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Broad marketing contacts")
    print(json.dumps(summary["counts"], indent=2))
    print(f"Wrote: {out_safe}")
    print(f"Wrote: {out_blocked}")
    print(f"Wrote: {out_review}")
    print(f"Wrote: {out_send}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
