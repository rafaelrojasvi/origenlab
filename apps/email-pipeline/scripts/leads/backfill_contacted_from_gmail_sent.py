#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY: --apply writes outreach_contact_state. Default is dry-run (no DB writes).
# See docs/SCRIPT_MAP.md — "Break-glass scripts" for other --apply tools.
# -----------------------------------------------------------------------------
"""Backfill outreach_contact_state=contacted from Gmail Sent history.

Safe defaults:
- dry-run unless --apply is passed
- read-only inspection of emails table
- does not send emails
- does not change gate logic
- does not modify emails table
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.marketing_export_context import DEFAULT_EXCLUDE_DOMAINS
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)
from origenlab_email_pipeline.outreach_contact_state import (
    ensure_outreach_contact_state_table,
    fetch_outreach_contact_state_row,
    outreach_contact_state_table_exists,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)
from origenlab_email_pipeline.timeutil import now_iso


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _sent_recipient_date_bounds(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> tuple[dict[str, tuple[str, str]], int]:
    if not _table_exists(conn, "emails"):
        return {}, 0
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return {}, 0
    like_pat = f"gmail:{user}/%".lower()
    ph = ",".join("?" * len(folders))
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(emails)").fetchall()}
    date_expr = (
        "COALESCE(NULLIF(TRIM(date_iso), ''), NULLIF(TRIM(date_raw), ''), '')"
        if "date_raw" in cols
        else "COALESCE(NULLIF(TRIM(date_iso), ''), '')"
    )
    cur = conn.execute(
        f"""
        SELECT recipients, {date_expr} AS dts
        FROM emails
        WHERE lower(source_file) LIKE ?
          AND folder IN ({ph})
        """,
        (like_pat, *folders),
    )
    out: dict[str, tuple[str, str]] = {}
    n_rows = 0
    for recipients, dts in cur:
        n_rows += 1
        ds = str(dts or "").strip()
        if not recipients:
            continue
        for em in emails_in(recipients):
            prev = out.get(em)
            if prev is None:
                out[em] = (ds, ds)
                continue
            old_min, old_max = prev
            new_min = ds if ds and (not old_min or ds < old_min) else old_min
            new_max = ds if ds and (not old_max or ds > old_max) else old_max
            out[em] = (new_min, new_max)
    return out, n_rows


def _email_domain(email: str) -> str:
    p = email.rpartition("@")
    return p[2].strip().lower() if p[1] else ""


def _state_blocks_outbound(state: str) -> bool:
    return state in {"contacted", "replied", "snoozed"}


def _build_summary(
    *,
    dry_run: bool,
    db_path: Path,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    source: str,
    updated_by: str,
    sent_unique: int,
    existing_state: int,
    missing_state: int,
    would_insert: int,
    skipped_existing: int,
    skipped_invalid: int,
    skipped_internal: int,
    applied_inserts: int,
    applied_updates: int,
    sampled_backfill: list[str],
    limit: int | None,
    sent_email_rows_scanned: int,
) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry_run,
        "db_path": str(db_path),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
        "source": source,
        "updated_by": updated_by,
        "limit": limit,
        "sent_email_rows_scanned": sent_email_rows_scanned,
        "sent_unique": sent_unique,
        "existing_state": existing_state,
        "missing_state": missing_state,
        "would_insert": would_insert,
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
        "skipped_internal": skipped_internal,
        "applied_inserts": applied_inserts,
        "applied_updates": applied_updates,
        "sample_backfill_emails": sampled_backfill,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--gmail-user", default=None, help="Override Gmail mailbox for Sent scan")
    ap.add_argument("--sent-folder", action="append", default=[], help="Sent folder label (repeatable)")
    ap.add_argument("--apply", action="store_true", help="Write outreach_contact_state updates (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="Explicit alias for dry-run mode")
    ap.add_argument("--updated-by", default="gmail_sent_backfill", help="Audit actor")
    ap.add_argument("--source", default="gmail_sent_backfill", help="State provenance label")
    ap.add_argument("--json-out", type=Path, default=None, help="Optional output JSON path")
    ap.add_argument("--limit", type=int, default=None, help="Limit candidate backfills")
    ap.add_argument(
        "--exclude-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip emails already present in outreach_contact_state (default: true)",
    )
    args = ap.parse_args(argv)

    do_apply = bool(args.apply)
    if args.dry_run:
        do_apply = False

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite file not found: {db_path}", file=sys.stderr)
        return 1
    if args.limit is not None and args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    ro_conn = _connect_readonly(db_path)
    try:
        sent_bounds, sent_rows = _sent_recipient_date_bounds(
            ro_conn, gmail_user=gmail_user, sent_folders=sent_folders
        )
        existing_state_set: set[str] = set()
        if outreach_contact_state_table_exists(ro_conn):
            rows = ro_conn.execute(
                """
                SELECT lower(trim(contact_email_norm)) AS e
                FROM outreach_contact_state
                WHERE state IN ('contacted', 'replied', 'snoozed')
                  AND length(trim(contact_email_norm)) > 0
                """
            ).fetchall()
            existing_state_set = {str(r[0]) for r in rows if r[0]}
    finally:
        ro_conn.close()

    sent_emails = sorted(sent_bounds.keys())
    if args.limit is not None:
        sent_emails = sent_emails[: args.limit]

    internal_domains = {d.strip().lower() for d in DEFAULT_EXCLUDE_DOMAINS if d.strip()}
    skipped_invalid = 0
    skipped_internal = 0
    skipped_existing = 0
    missing_candidates: list[str] = []
    update_candidates: list[str] = []

    for em in sent_emails:
        if "@" not in em:
            skipped_invalid += 1
            continue
        if _email_domain(em) in internal_domains:
            skipped_internal += 1
            continue
        if em in existing_state_set:
            skipped_existing += 1
            continue
        missing_candidates.append(em)

    if not args.exclude_existing:
        ro_conn2 = _connect_readonly(db_path)
        try:
            if _table_exists(ro_conn2, "outreach_contact_state"):
                rows = ro_conn2.execute(
                    """
                    SELECT lower(trim(contact_email_norm)) AS e, lower(trim(state)) AS st
                    FROM outreach_contact_state
                    WHERE length(trim(contact_email_norm)) > 0
                    """
                ).fetchall()
                state_map = {str(e): str(st or "") for e, st in rows if e}
            else:
                state_map = {}
        finally:
            ro_conn2.close()
        for em in sent_emails:
            if em in missing_candidates:
                continue
            st = state_map.get(em)
            if not st or _state_blocks_outbound(st):
                continue
            if _email_domain(em) in internal_domains:
                continue
            update_candidates.append(em)

    sampled = missing_candidates[:20]
    summary = _build_summary(
        dry_run=not do_apply,
        db_path=db_path,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        source=args.source,
        updated_by=args.updated_by,
        sent_unique=len(sent_emails),
        existing_state=len(existing_state_set),
        missing_state=len(missing_candidates),
        would_insert=len(missing_candidates),
        skipped_existing=skipped_existing,
        skipped_invalid=skipped_invalid,
        skipped_internal=skipped_internal,
        applied_inserts=0,
        applied_updates=0,
        sampled_backfill=sampled,
        limit=args.limit,
        sent_email_rows_scanned=sent_rows,
    )

    if not do_apply:
        print("Dry-run sample (first 20 emails to backfill):")
        for em in sampled:
            print(f"  - {em}")
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        print(text)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(text, encoding="utf-8")
        return 0

    conn = connect(db_path)
    try:
        ensure_outreach_contact_state_table(conn)
        inserts = 0
        updates = 0
        for em in missing_candidates + update_candidates:
            existing = fetch_outreach_contact_state_row(conn, em)
            earliest, latest = sent_bounds.get(em, ("", ""))
            touch = now_iso()
            first_ts = earliest or touch
            if existing and existing.get("first_contacted_at"):
                prev_first = str(existing.get("first_contacted_at") or "").strip()
                if prev_first:
                    first_ts = prev_first
            last_ts = latest or touch
            payload = validate_outreach_contact_state_payload(
                contact_email=em,
                state="contacted",
                first_contacted_at=first_ts,
                last_contacted_at=last_ts,
                source=args.source,
                notes="Backfilled from Gmail Sent history",
                updated_by=args.updated_by,
                lead_id=int(existing["lead_id"]) if existing and existing.get("lead_id") is not None else None,
            )
            upsert_outreach_contact_state(conn, payload=payload, at_iso=touch)
            if existing is None:
                inserts += 1
            else:
                updates += 1
        conn.commit()
    finally:
        conn.close()

    summary["applied_inserts"] = inserts
    summary["applied_updates"] = updates
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
