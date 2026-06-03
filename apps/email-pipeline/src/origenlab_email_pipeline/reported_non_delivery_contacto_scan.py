"""Read-only scan for inbound human-reported non-delivery on contacto Gmail ingest."""

from __future__ import annotations

import sqlite3
from typing import Any

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.reported_non_delivery_signals import text_suggests_reported_non_delivery

_INTERNAL_DOMAIN_SUFFIXES: tuple[str, ...] = ("origenlab.cl", "labdelivery.cl")

ReportedNonDeliveryEntry = tuple[str, str | None, int, str | None]
# contact_email -> (date_iso, email_id, subject_snip)


def is_internal_or_system_sender(sender: str) -> bool:
    s = (sender or "").lower()
    if "mailer-daemon" in s or "postmaster@" in s or "mail delivery subsystem" in s:
        return True
    found = emails_in(sender)
    if not found:
        return True
    dom = found[0].split("@", 1)[-1]
    return any(dom == suf or dom.endswith("." + suf) for suf in _INTERNAL_DOMAIN_SUFFIXES)


def scan_reported_non_delivery_senders(
    conn: sqlite3.Connection,
    *,
    since_days: int | None,
    limit: int,
) -> tuple[dict[str, ReportedNonDeliveryEntry], int]:
    """Scan non-sent contacto rows for human-reported non-delivery phrasing.

    Returns ``(planned_by_email, rows_scanned)``. Suppression code is always
    ``reported_non_delivery`` (applied by the canonical CLI, not here).
    """
    pred = sql_predicate_contacto_gmail_source()
    date_filter = ""
    params: list[Any] = []
    if since_days is not None and since_days > 0:
        date_filter = "AND date_iso >= date('now', ?)"
        params.append(f"-{int(since_days)} days")

    sql = f"""
        SELECT sender, subject, body_text_clean, body, full_body_clean,
               folder, date_iso, id
        FROM emails
        WHERE {pred}
          AND lower(coalesce(folder, '')) NOT LIKE '%enviad%'
          AND lower(coalesce(folder, '')) NOT LIKE '%sent%'
          {date_filter}
        ORDER BY COALESCE(date_iso, '') DESC
        LIMIT ?
    """
    params.append(int(limit))

    planned: dict[str, ReportedNonDeliveryEntry] = {}
    scanned = 0
    cur = conn.execute(sql, tuple(params))
    for sender, subject, body_text_clean, body, full_body_clean, _folder, date_iso, eid in cur:
        scanned += 1
        if is_internal_or_system_sender(str(sender or "")):
            continue
        body_blob = (
            str(body_text_clean or "")
            or str(full_body_clean or "")
            or str(body or "")
        )
        if not text_suggests_reported_non_delivery(
            str(subject) if subject else None,
            body_blob or None,
        ):
            continue
        found = emails_in(str(sender or ""))
        if not found:
            continue
        email = found[0].lower()
        subj_snip = (str(subject)[:100] + "…") if subject and len(str(subject)) > 100 else subject
        d_iso = str(date_iso) if date_iso else None
        prev = planned.get(email)
        if prev is None or (d_iso or "") > (prev[0] or ""):
            planned[email] = (d_iso, int(eid), subj_snip)

    return planned, scanned
