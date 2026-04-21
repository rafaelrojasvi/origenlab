#!/usr/bin/env python3
"""Mark a sent batch as contacted in outreach_contact_state (SQLite sidecar).

This command is a post-send memory update only:
- does not send emails
- does not change export gate logic
- does not write suppression tables

It supports recipient input from either a plain/CSV/TSV batch file or a JSON send manifest.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outreach_contact_state import (
    ensure_outreach_contact_state_table,
    fetch_outreach_contact_state_row,
    outreach_touch_timestamps_for_upsert,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)
from origenlab_email_pipeline.timeutil import now_iso

_EMAIL_FIELDS = (
    "contact_email",
    "email",
    "to",
    "recipient_email",
    "recipient",
    "real_to",
    "effective_to",
)


def _extract_first_email(text: str) -> str | None:
    found = emails_in(str(text or ""))
    if not found:
        return None
    return found[0].strip().lower()


def _looks_tabular_header(line: str) -> bool:
    l = (line or "").strip().lower()
    if not l:
        return False
    if "," in l or "\t" in l:
        return any(f in l for f in _EMAIL_FIELDS)
    return False


def _parse_batch_file(path: Path) -> tuple[list[str], int, list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    first_nonempty = next((ln for ln in lines if ln.strip()), "")
    warnings: list[str] = []
    candidates: list[str] = []
    total_input = 0

    is_tabular = path.suffix.lower() in {".csv", ".tsv"} or ("," in first_nonempty or "\t" in first_nonempty)
    if is_tabular:
        delim = "\t" if path.suffix.lower() == ".tsv" or "\t" in first_nonempty else ","
        reader = csv.DictReader(lines, delimiter=delim)
        if reader.fieldnames:
            lower_fields = [str(f or "").strip().lower() for f in reader.fieldnames]
            if not any(f in lower_fields for f in _EMAIL_FIELDS):
                warnings.append(
                    "Input looks like tabular data with headers but no known email column "
                    f"({', '.join(_EMAIL_FIELDS)})."
                )
        for row in reader:
            total_input += 1
            extracted: str | None = None
            for key in _EMAIL_FIELDS:
                if key in row:
                    extracted = _extract_first_email(str(row.get(key) or ""))
                    if extracted:
                        break
            if extracted:
                candidates.append(extracted)
        return candidates, total_input, warnings

    if _looks_tabular_header(first_nonempty):
        warnings.append(
            "Input appears to contain a CSV/TSV header. If parsing looks wrong, pass a proper CSV/TSV file."
        )
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        total_input += 1
        em = _extract_first_email(s)
        if em:
            candidates.append(em)
    return candidates, total_input, warnings


def _add_manifest_emails(node: Any, out: list[str], counter: dict[str, int]) -> None:
    if isinstance(node, str):
        counter["total"] += 1
        em = _extract_first_email(node)
        if em:
            out.append(em)
        return
    if isinstance(node, list):
        for item in node:
            _add_manifest_emails(item, out, counter)
        return
    if isinstance(node, dict):
        for key in _EMAIL_FIELDS:
            if key in node:
                counter["total"] += 1
                em = _extract_first_email(str(node.get(key) or ""))
                if em:
                    out.append(em)
        for key in ("recipients", "to", "emails", "sent_recipients", "results", "messages"):
            if key in node:
                _add_manifest_emails(node[key], out, counter)


def _parse_send_manifest(path: Path) -> tuple[list[str], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    counter = {"total": 0}
    _add_manifest_emails(payload, out, counter)
    return out, int(counter["total"])


def _touch_iso_after(existing_last: str | None) -> str:
    ts = now_iso()
    if not existing_last:
        return ts
    try:
        prev = datetime.fromisoformat(str(existing_last).replace("Z", "+00:00"))
        cur = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    if cur <= prev:
        nxt = prev + timedelta(seconds=1)
        return nxt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return ts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--batch-file",
        action="append",
        type=Path,
        default=[],
        help="Recipients file: one per line, CSV, or TSV (repeatable).",
    )
    ap.add_argument("--send-manifest", type=Path, default=None, help="JSON send manifest containing recipients.")
    ap.add_argument("--source", required=True, help="Required provenance label, e.g. manual_html_batch_2026_04_21.")
    ap.add_argument("--notes", default=None, help="Optional notes stored in outreach_contact_state.")
    ap.add_argument("--updated-by", default="mark_sent_batch_contacted.py", help="Audit actor.")
    ap.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    ap.add_argument("--json-out", type=Path, default=None, help="Optional output JSON path.")
    args = ap.parse_args(argv)

    if not args.batch_file and not args.send_manifest:
        print("Provide --batch-file and/or --send-manifest.", file=sys.stderr)
        return 2

    batch_candidates: list[str] = []
    total_input = 0
    warnings: list[str] = []
    for batch_file in args.batch_file:
        if not batch_file.is_file():
            print(f"Batch file not found: {batch_file}", file=sys.stderr)
            return 1
        cands, n_total, warns = _parse_batch_file(batch_file)
        batch_candidates.extend(cands)
        total_input += n_total
        warnings.extend(warns)

    if args.send_manifest:
        if not args.send_manifest.is_file():
            print(f"Send manifest not found: {args.send_manifest}", file=sys.stderr)
            return 1
        try:
            cands, n_total = _parse_send_manifest(args.send_manifest)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON in --send-manifest: {exc}", file=sys.stderr)
            return 2
        batch_candidates.extend(cands)
        total_input += n_total

    unique_valid: list[str] = []
    seen: set[str] = set()
    for em in batch_candidates:
        if em not in seen:
            seen.add(em)
            unique_valid.append(em)

    invalid_skipped = max(0, total_input - len(batch_candidates))
    if not unique_valid:
        print("No valid recipient emails found to mark as contacted.", file=sys.stderr)
        return 2

    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite file not found: {db_path}", file=sys.stderr)
        return 1

    summary: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "db_path": str(db_path),
        "source": str(args.source),
        "notes": args.notes,
        "updated_by": args.updated_by,
        "total_input": total_input,
        "normalized_unique": len(unique_valid),
        "inserted": 0,
        "updated": 0,
        "already_contacted": 0,
        "invalid_or_skipped": invalid_skipped,
        "emails": unique_valid,
        "warnings": warnings,
    }

    if args.dry_run:
        if warnings:
            for w in warnings:
                print(f"warning: {w}", file=sys.stderr)
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        print(text)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(text, encoding="utf-8")
        return 0

    conn = connect(db_path)
    try:
        ensure_outreach_contact_state_table(conn)
        for em in unique_valid:
            existing = fetch_outreach_contact_state_row(conn, em)
            if existing is None:
                summary["inserted"] += 1
            else:
                if str(existing.get("state") or "").strip().lower() == "contacted":
                    summary["already_contacted"] += 1
                else:
                    summary["updated"] += 1
            ts = _touch_iso_after(
                str(existing.get("last_contacted_at") or "").strip() if existing else None
            )
            first, last = outreach_touch_timestamps_for_upsert(
                new_state="contacted",
                existing_row=existing,
                touch_at_iso=ts,
            )
            payload = validate_outreach_contact_state_payload(
                contact_email=em,
                state="contacted",
                first_contacted_at=first,
                last_contacted_at=last,
                source=args.source,
                notes=args.notes,
                updated_by=args.updated_by,
                lead_id=int(existing["lead_id"]) if existing and existing.get("lead_id") is not None else None,
            )
            upsert_outreach_contact_state(conn, payload=payload, at_iso=ts)
        conn.commit()
    finally:
        conn.close()

    if warnings:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

