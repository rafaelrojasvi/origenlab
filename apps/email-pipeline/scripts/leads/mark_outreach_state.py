#!/usr/bin/env python3
"""Upsert ``outreach_contact_state`` (operator sidecar) for cold-outreach memory.

This is **manual** state only — it does **not** read Sent mail or auto-sync from the archive.

Gate semantics (``candidate_export_gate`` / ``marketing_export_context.load_outreach_state_map``):
  - ``contacted``, ``replied``, and ``snoozed`` **block** cold-export eligibility for that email.
  - ``not_contacted`` does **not** block (and clears first/last timestamps on upsert).

Examples::

  uv run python scripts/leads/mark_outreach_state.py \\
    --email contacto@cliente.cl --state contacted --updated-by rafael \\
    --source cli_batch_marzo --notes "Llamada 2026-04-12"

  uv run python scripts/leads/mark_outreach_state.py --db /path/to/emails.sqlite \\
    --email lead@uni.cl --state snoozed --updated-by rafael --notes "Revisar Q3"

  Batch (one mailbox per line; ``#`` comments and blank lines ignored; TSV lines OK — first  address parsed with ``emails_in`` wins)::

  uv run python scripts/leads/mark_outreach_state.py \\
    --batch-file reports/out/active/sent_contacts.txt \\
    --state contacted --updated-by rafael --source pilot_20260413
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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


def _emails_from_batch_file(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    out: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        found = emails_in(s)
        if not found:
            continue
        em = found[0]
        if em not in seen:
            seen.add(em)
            out.append(em)
    return out


def _upsert_one(
    conn,
    *,
    email: str,
    state: str,
    source: str,
    notes: str | None,
    updated_by: str,
    lead_id: int | None,
    print_json: bool,
) -> int:
    ensure_outreach_contact_state_table(conn)
    existing = fetch_outreach_contact_state_row(conn, email)
    ts = now_iso()
    first, last = outreach_touch_timestamps_for_upsert(
        new_state=state,
        existing_row=existing,
        touch_at_iso=ts,
    )
    try:
        payload = validate_outreach_contact_state_payload(
            contact_email=email,
            state=state,
            first_contacted_at=first,
            last_contacted_at=last,
            source=source,
            notes=notes,
            updated_by=updated_by,
            lead_id=lead_id,
        )
    except ValueError as e:
        print(f"{email}: {e}", file=sys.stderr)
        return 2

    upsert_outreach_contact_state(conn, payload=payload, at_iso=ts)

    saved = fetch_outreach_contact_state_row(conn, email)
    if not saved:
        print(f"{email}: upsert failed (row not readable).", file=sys.stderr)
        return 3
    if print_json:
        print(json.dumps(saved, ensure_ascii=False, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Blocking states for cold export: contacted, replied, snoozed. "
            "not_contacted does not block and clears first/last timestamps."
        ),
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--email",
        help="Single mailbox (normalized: trim, lower, one address — see emails_in rules).",
    )
    grp.add_argument(
        "--batch-file",
        type=Path,
        help="UTF-8 file: one mailbox per line (or TSV); parse addresses via emails_in.",
    )
    ap.add_argument(
        "--state",
        required=True,
        choices=("not_contacted", "contacted", "replied", "snoozed"),
        help="Outreach lifecycle state to store.",
    )
    ap.add_argument(
        "--source",
        default="mark_outreach_state.py",
        help="Short provenance string (stored in source column).",
    )
    ap.add_argument("--notes", default=None, help="Optional operator notes.")
    ap.add_argument(
        "--updated-by",
        default="mark_outreach_state.py",
        help="Who performed the change (audit column).",
    )
    ap.add_argument("--lead-id", type=int, default=None, help="Optional lead_master.id (positive int).")
    ap.add_argument(
        "--batch-print-json",
        action="store_true",
        help="With --batch-file, print one JSON object per line (default: summary only).",
    )
    args = ap.parse_args(argv)
    if args.batch_file is not None and args.lead_id is not None:
        print("--lead-id is not supported with --batch-file (one lead id per row).", file=sys.stderr)
        return 2

    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("SQLite file not found:", db_path, file=sys.stderr)
        return 1

    conn = connect(db_path)
    try:
        if args.batch_file:
            if not args.batch_file.is_file():
                print("Batch file not found:", args.batch_file, file=sys.stderr)
                return 1
            emails = _emails_from_batch_file(args.batch_file)
            if not emails:
                print("No parseable email addresses in batch file.", file=sys.stderr)
                return 2
            worst = 0
            for em in emails:
                rc = _upsert_one(
                    conn,
                    email=em,
                    state=args.state,
                    source=args.source,
                    notes=args.notes,
                    updated_by=args.updated_by,
                    lead_id=args.lead_id,
                    print_json=bool(args.batch_print_json),
                )
                worst = max(worst, rc)
            conn.commit()
            if not args.batch_print_json:
                print(
                    json.dumps(
                        {"ok": True, "count": len(emails), "emails": emails},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return worst

        rc = _upsert_one(
            conn,
            email=args.email or "",
            state=args.state,
            source=args.source,
            notes=args.notes,
            updated_by=args.updated_by,
            lead_id=args.lead_id,
            print_json=True,
        )
        if rc == 0:
            conn.commit()
        return rc
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
