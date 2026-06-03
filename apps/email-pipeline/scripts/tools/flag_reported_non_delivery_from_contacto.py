#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): --apply writes contact_email_suppression. Default is print-only.
# See docs/SCRIPT_MAP.md — "Break-glass scripts".
# -----------------------------------------------------------------------------
"""Scan contacto@origenlab.cl Gmail-ingested mail for "never got your email" style replies.

**Inbound only** (excludes Sent/Enviados): uses ``sender`` as the contact to flag.

Writes ``contact_email_suppression`` with ``reported_non_delivery`` (same hard exclude as bounces).

Default is print-only; use ``--apply`` after you agree with the matches.

Example::

  uv run python scripts/tools/flag_reported_non_delivery_from_contacto.py --limit 500
  uv run python scripts/tools/flag_reported_non_delivery_from_contacto.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_email_suppression import (
    ensure_contact_email_suppression_table,
    fetch_contact_email_suppression_row,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.core.safety import print_script_deprecation_warning
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.reported_non_delivery_signals import text_suggests_reported_non_delivery

_INTERNAL_DOMAIN_SUFFIXES: tuple[str, ...] = ("origenlab.cl", "labdelivery.cl")


def _is_internal_or_system_sender(sender: str) -> bool:
    s = (sender or "").lower()
    if "mailer-daemon" in s or "postmaster@" in s or "mail delivery subsystem" in s:
        return True
    found = emails_in(sender)
    if not found:
        return True
    dom = found[0].split("@", 1)[-1]
    return any(dom == suf or dom.endswith("." + suf) for suf in _INTERNAL_DOMAIN_SUFFIXES)


def main() -> int:
    print_script_deprecation_warning(
        "scripts/tools/flag_reported_non_delivery_from_contacto.py",
        replacement=(
            "scripts/tools/flag_ndr_bounces_from_contacto.py "
            "(NDR default; add --include-reported-non-delivery for human-reported inbound)"
        ),
        note=(
            'Human "reported non-delivery" inbound replies: use canonical tool with '
            "--include-reported-non-delivery; review matches carefully before --apply."
        ),
    )
    ap = argparse.ArgumentParser(
        description="Flag contacts who wrote (.Spanish/English.) that they did not receive our mail."
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Upsert contact_email_suppression rows (default: print matches only).",
    )
    ap.add_argument("--limit", type=int, default=50_000, help="Max rows to scan from inbox side.")
    args = ap.parse_args()

    db_path = args.db or load_settings().resolved_sqlite_path()
    pred = sql_predicate_contacto_gmail_source()
    sql = f"""
        SELECT sender, subject, body_text_clean, folder, date_iso, id
        FROM emails
        WHERE {pred}
          AND lower(coalesce(folder, '')) NOT LIKE '%enviad%'
          AND lower(coalesce(folder, '')) NOT LIKE '%sent%'
        ORDER BY COALESCE(date_iso, '') DESC
        LIMIT ?
    """

    conn = connect(db_path)
    try:
        cur = conn.execute(sql, (int(args.limit),))
        hits: list[tuple[str, str | None, str | None, str | None, int]] = []
        for sender, subject, body, folder, date_iso, eid in cur:
            if _is_internal_or_system_sender(str(sender or "")):
                continue
            if not text_suggests_reported_non_delivery(
                str(subject) if subject else None,
                str(body) if body else None,
            ):
                continue
            found = emails_in(str(sender or ""))
            if not found:
                continue
            email = found[0]
            hits.append((email, str(subject) if subject else None, str(folder) if folder else None, str(date_iso) if date_iso else None, int(eid)))

        seen: set[str] = set()
        unique_hits: list[tuple[str, str | None, str | None, str | None, int]] = []
        for row in hits:
            if row[0] in seen:
                continue
            seen.add(row[0])
            unique_hits.append(row)

        print(f"Scanned up to {args.limit} recent non-sent contacto rows; {len(unique_hits)} distinct sender(s) matched.")
        for email, subj, folder, date_iso, eid in unique_hits:
            print(f"  - {email}  email_id={eid}  folder={folder}  date_iso={date_iso}")
            if subj:
                print(f"      subject: {(subj[:120] + '…') if len(subj) > 120 else subj}")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to write suppressions.")
            return 0

        ensure_contact_email_suppression_table(conn)
        n = 0
        skipped_existing = 0
        for email, _subj, _folder, date_iso, eid in unique_hits:
            existing = fetch_contact_email_suppression_row(conn, email)
            if existing and str(existing.get("suppression_reason_code") or "") != "reported_non_delivery":
                print(
                    f"  skip (already suppressed as {existing.get('suppression_reason_code')}): {email}",
                    file=sys.stderr,
                )
                skipped_existing += 1
                continue
            payload = validate_contact_email_suppression_payload(
                email=email,
                suppression_reason_code="reported_non_delivery",
                suppression_reason_text=f"Heuristic inbound from contacto Gmail (email id {eid})",
                suppression_source="flag_reported_non_delivery_from_contacto.py",
                last_bounced_at=None,
                updated_by="flag_reported_non_delivery_from_contacto.py",
            )
            upsert_contact_email_suppression(conn, payload=payload)
            n += 1
        conn.commit()
        print(f"Upserted reported_non_delivery: {n} row(s); skipped_existing_other_reason: {skipped_existing}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
