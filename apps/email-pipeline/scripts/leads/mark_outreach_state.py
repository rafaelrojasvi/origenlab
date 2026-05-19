#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY — Manual outreach_contact_state edits (operator sidecar).
# Default: dry-run preview only. Writes require --apply plus operator, source, reason.
# Does not read Sent mail, ingest Gmail, or send email.
# -----------------------------------------------------------------------------
"""Upsert ``outreach_contact_state`` (operator sidecar) for cold-outreach memory.

Dry-run by default. Use ``--apply`` to mutate ``outreach_contact_state``.

This is **manual** state only — it does **not** read Sent mail or auto-sync from the archive.

Gate semantics (``candidate_export_gate`` / ``marketing_export_context.load_outreach_state_map``):
  - ``contacted``, ``replied``, and ``snoozed`` **block** cold-export eligibility for that email.
  - ``not_contacted`` does **not** block (and clears first/last timestamps on upsert).

Examples::

  # Preview (default — no DB write)
  uv run python scripts/leads/mark_outreach_state.py \\
    --email contacto@cliente.cl --state contacted --updated-by rafael \\
    --source cli_batch_marzo --reason "Llamada 2026-04-12" --notes "optional"

  # Apply after review
  uv run python scripts/leads/mark_outreach_state.py --apply \\
    --email contacto@cliente.cl --state contacted --operator rafael \\
    --source-artifact cli_batch_marzo --reason "Llamada 2026-04-12"

  Batch (one mailbox per line; ``#`` comments and blank lines ignored)::

  uv run python scripts/leads/mark_outreach_state.py --apply \\
    --batch-file reports/out/active/sent_contacts.txt \\
    --state contacted --updated-by rafael --source pilot_20260413 \\
    --reason "Manual HTML batch marked contacted"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.core.safety import require_apply_for_mutation
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outreach_contact_state import (
    ensure_outreach_contact_state_table,
    fetch_outreach_contact_state_row,
    outreach_touch_timestamps_for_upsert,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)
from origenlab_email_pipeline.timeutil import now_iso

_SAFETY_DESCRIPTION = (
    "Upsert outreach_contact_state (operator sidecar). "
    "Dry-run by default. Use --apply to mutate outreach_contact_state."
)


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


def _resolve_pair(
    primary: str | None,
    alias: str | None,
    *,
    primary_flag: str,
    alias_flag: str,
) -> tuple[str | None, str | None]:
    p = (primary or "").strip()
    a = (alias or "").strip()
    if p and a and p != a:
        return None, f"Conflicting {primary_flag} and {alias_flag}."
    value = p or a or None
    if not value:
        return None, f"Missing {primary_flag} or {alias_flag}."
    return value, None


def _resolve_audit_fields(args: argparse.Namespace) -> tuple[str, str, str, str | None]:
    """Return (updated_by, source, reason, error_message)."""
    updated_by, err = _resolve_pair(
        args.updated_by,
        args.operator,
        primary_flag="--updated-by",
        alias_flag="--operator",
    )
    if err:
        return "", "", "", err
    source, err = _resolve_pair(
        args.source,
        args.source_artifact,
        primary_flag="--source",
        alias_flag="--source-artifact",
    )
    if err:
        return "", "", "", err
    reason = (args.reason or "").strip()
    if not reason:
        return "", "", "", "Missing --reason."
    assert updated_by is not None and source is not None
    return updated_by, source, reason, None


def _preview_record(
    *,
    contact_email_norm: str,
    old_state: str | None,
    new_state: str,
    source: str,
    updated_by: str,
    reason: str,
    notes: str | None,
) -> dict[str, Any]:
    return {
        "dry_run": True,
        "contact_email_norm": contact_email_norm,
        "old_state": old_state,
        "new_state": new_state,
        "source": source,
        "updated_by": updated_by,
        "reason": reason,
        "notes": notes,
    }


def _plan_one(
    conn,
    *,
    email: str,
    state: str,
    source: str,
    notes: str | None,
    updated_by: str,
    reason: str,
    lead_id: int | None,
) -> tuple[dict[str, Any] | None, int]:
    ensure_outreach_contact_state_table(conn)
    existing = fetch_outreach_contact_state_row(conn, email)
    old_state = existing.get("state") if existing else None
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
        return None, 2

    return (
        _preview_record(
            contact_email_norm=payload.contact_email_norm,
            old_state=old_state,
            new_state=state,
            source=source,
            updated_by=updated_by,
            reason=reason,
            notes=notes,
        ),
        0,
    )


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
    require_apply_for_mutation(True, "outreach_contact_state upsert")
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=_SAFETY_DESCRIPTION,
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
        default=None,
        help="Short provenance string (stored in source column). Alias: --source-artifact.",
    )
    ap.add_argument(
        "--source-artifact",
        default=None,
        help="Alias for --source (campaign slug, manifest path, etc.).",
    )
    ap.add_argument("--notes", default=None, help="Optional operator notes.")
    ap.add_argument(
        "--updated-by",
        default=None,
        help="Who performed the change (audit column). Alias: --operator.",
    )
    ap.add_argument(
        "--operator",
        default=None,
        help="Alias for --updated-by.",
    )
    ap.add_argument(
        "--reason",
        default=None,
        help="Required human-readable reason for the change (dry-run and --apply).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write to outreach_contact_state (default is preview only).",
    )
    ap.add_argument("--lead-id", type=int, default=None, help="Optional lead_master.id (positive int).")
    ap.add_argument(
        "--batch-print-json",
        action="store_true",
        help="With --batch-file, print one JSON object per line (default: summary only).",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_file is not None and args.lead_id is not None:
        print("--lead-id is not supported with --batch-file (one lead id per row).", file=sys.stderr)
        return 2

    updated_by, source, reason, audit_err = _resolve_audit_fields(args)
    if audit_err:
        print(f"ERROR: {audit_err}", file=sys.stderr)
        return 2

    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("SQLite file not found:", db_path, file=sys.stderr)
        return 1

    apply = bool(args.apply)
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
            previews: list[dict[str, Any]] = []
            for em in emails:
                if apply:
                    rc = _upsert_one(
                        conn,
                        email=em,
                        state=args.state,
                        source=source,
                        notes=args.notes,
                        updated_by=updated_by,
                        lead_id=args.lead_id,
                        print_json=bool(args.batch_print_json),
                    )
                else:
                    preview, rc = _plan_one(
                        conn,
                        email=em,
                        state=args.state,
                        source=source,
                        notes=args.notes,
                        updated_by=updated_by,
                        reason=reason,
                        lead_id=args.lead_id,
                    )
                    if preview is not None:
                        previews.append(preview)
                        if args.batch_print_json:
                            print(json.dumps(preview, ensure_ascii=False, default=str))
                worst = max(worst, rc)

            if apply:
                conn.commit()
                if not args.batch_print_json:
                    print(
                        json.dumps(
                            {"ok": True, "applied": True, "count": len(emails), "emails": emails},
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
            elif not args.batch_print_json:
                print(
                    json.dumps(
                        {
                            "dry_run": True,
                            "count": len(previews),
                            "previews": previews,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return worst

        if apply:
            rc = _upsert_one(
                conn,
                email=args.email or "",
                state=args.state,
                source=source,
                notes=args.notes,
                updated_by=updated_by,
                lead_id=args.lead_id,
                print_json=True,
            )
            if rc == 0:
                conn.commit()
            return rc

        preview, rc = _plan_one(
            conn,
            email=args.email or "",
            state=args.state,
            source=source,
            notes=args.notes,
            updated_by=updated_by,
            reason=reason,
            lead_id=args.lead_id,
        )
        if preview is not None:
            print(json.dumps(preview, ensure_ascii=False, default=str))
        return rc
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
