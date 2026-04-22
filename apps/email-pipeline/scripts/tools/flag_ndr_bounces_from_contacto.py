#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): --apply writes contact_email_suppression. Default is print-only.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Scan contacto@origenlab Gmail-ingested mail for NDR / Mailer-Daemon bounces.

Reads ``emails`` rows whose ``source_file`` is the workspace ingest prefix, keeps rows
classified as ``bounce_ndr``, extracts failed recipient(s) from the DSN body, and optionally
writes ``contact_email_suppression`` with ``bounce_no_such_user`` / ``bounce_access_denied`` /
``bounce_other``.

Default is print-only; use ``--apply`` after reviewing matches.

Example::

  uv run python scripts/tools/flag_ndr_bounces_from_contacto.py --since-days 30 --limit 20000
  uv run python scripts/tools/flag_ndr_bounces_from_contacto.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_email_suppression import (
    ensure_contact_email_suppression_table,
    fetch_contact_email_suppression_row,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.email_business_filters import classify_email
from origenlab_email_pipeline.ndr_bounce_extraction import (
    bounce_suppression_code_from_ndr_text,
    extract_failed_recipients_from_ndr,
)


def _body_blob(row: tuple) -> str:
    full_clean, text_clean, body = row
    return (
        str(full_clean or "")
        or str(text_clean or "")
        or str(body or "")
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Upsert contact_email_suppression for extracted recipients.",
    )
    ap.add_argument("--limit", type=int, default=50_000, help="Max NDR-shaped rows to scan")
    ap.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only rows with date_iso >= now - N days (SQLite date string compare is lexical ISO).",
    )
    args = ap.parse_args()

    db_path = args.db or load_settings().resolved_sqlite_path()
    pred = sql_predicate_contacto_gmail_source()

    date_filter = ""
    params: list = []
    if args.since_days is not None and args.since_days > 0:
        date_filter = "AND date_iso >= date('now', ?)"
        params.append(f"-{int(args.since_days)} days")

    sql = f"""
        SELECT sender, subject,
               full_body_clean, body_text_clean, body,
               folder, date_iso, id
        FROM emails
        WHERE {pred}
        {date_filter}
        ORDER BY COALESCE(date_iso, '') DESC
        LIMIT ?
    """
    params.append(int(args.limit))

    conn = connect(db_path)
    try:
        cur = conn.execute(sql, tuple(params))
        # recipient_email -> (code, date_iso, email_id, subject_snip)
        planned: dict[str, tuple[str, str | None, int, str | None]] = {}
        skipped_no_rcpt = 0
        scanned = 0
        for sender, subject, full_clean, text_clean, body, folder, date_iso, eid in cur:
            scanned += 1
            blob = _body_blob((full_clean, text_clean, body))
            cl = classify_email(sender=str(sender or ""), subject=str(subject or ""), body=blob)
            if "bounce_ndr" not in cl.get("tags", []):
                continue
            subj_l = str(subject or "").lower()
            if "notification (delay)" in subj_l or subj_l.strip().endswith("(delay)"):
                continue
            rcpts = extract_failed_recipients_from_ndr(blob)
            if not rcpts:
                skipped_no_rcpt += 1
                continue
            code = bounce_suppression_code_from_ndr_text(blob)
            subj_snip = (str(subject)[:100] + "…") if subject and len(str(subject)) > 100 else subject
            d_iso = str(date_iso) if date_iso else None
            for r in rcpts:
                prev = planned.get(r)
                if prev is None or (d_iso or "") > (prev[1] or ""):
                    planned[r] = (code, d_iso, int(eid), subj_snip)

        print(
            f"Scanned {scanned} recent contacto row(s); "
            f"bounce_ndr with extracted recipient: {len(planned)} distinct address(es); "
            f"bounce_ndr but no address parsed: {skipped_no_rcpt}."
        )
        for email in sorted(planned.keys()):
            code, d_iso, eid, subj_snip = planned[email]
            extra = f"  email_id={eid}  date_iso={d_iso or '—'}"
            if subj_snip:
                extra += f"\n      subject: {subj_snip}"
            print(f"  - {email}  → {code}{extra}")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to write suppressions.")
            return 0

        ensure_contact_email_suppression_table(conn)
        n = 0
        skipped_manual = 0
        for email, (code, d_iso, eid, _subj) in sorted(planned.items()):
            existing = fetch_contact_email_suppression_row(conn, email)
            if existing and str(existing.get("suppression_reason_code") or "") == "manual_do_not_contact":
                print(f"  skip (manual_do_not_contact): {email}", file=sys.stderr)
                skipped_manual += 1
                continue
            payload = validate_contact_email_suppression_payload(
                email=email,
                suppression_reason_code=code,
                suppression_reason_text=f"NDR from contacto Gmail ingest (source email id {eid})",
                suppression_source="flag_ndr_bounces_from_contacto.py",
                last_bounced_at=d_iso,
                updated_by="flag_ndr_bounces_from_contacto.py",
            )
            upsert_contact_email_suppression(conn, payload=payload)
            n += 1
        conn.commit()
        print(f"Upserted bounce suppressions: {n} row(s); skipped_manual: {skipped_manual}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
