"""Match a manual outreach recipient list to ingested NDR/bounce mail in SQLite.

Only flags addresses that appear in **both** the operator batch list and the body/subject
of a message classified as ``bounce_ndr`` (see ``email_business_filters.classify_email``).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta, timezone

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.email_business_filters import classify_email
from origenlab_email_pipeline.ndr_bounce_extraction import extract_failed_recipients_from_ndr

# Spanish / English phrases in Gmail-hosted DSN snippets (body may be short).
_EXTRA_BOUNCE_SUBJECT_FRAGMENTS = (
    "no se entregó",
    "no se entrego",
    "dirección no se encuentra",
    "direccion no se encuentra",
)

_NO_SUCH_USER_MARKERS = (
    "5.1.1",
    "5.1.0",
    "550 5.1.1",
    "user unknown",
    "unknown user",
    "no such user",
    "address not found",
    "does not exist",
    "recipient not found",
    "mailbox unavailable",
    "invalid recipient",
    "usuario inexistente",
    "no existe",
    "casilla no existe",
    "recipient address rejected",
    "requested action not taken: mailbox unavailable",
)


def _utc_today() -> date:
    from datetime import datetime

    return datetime.now(timezone.utc).date()


def cutoff_date_str(*, since_days: int) -> str:
    """Inclusive calendar cutoff ``YYYY-MM-DD`` for ``date_iso`` / ``date_raw`` prefixes."""
    d = max(0, int(since_days))
    return (_utc_today() - timedelta(days=d)).isoformat()


def load_batch_emails_from_file(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        found = emails_in(s)
        if not found:
            continue
        em = found[0].strip().lower()
        if em not in seen:
            seen.add(em)
            out.append(em)
    return out


def _ndr_blob_from_row(row: Mapping[str, object] | sqlite3.Row) -> str:
    def _g(key: str) -> str:
        if isinstance(row, sqlite3.Row):
            try:
                v = row[key]
            except (KeyError, IndexError):
                v = None
        else:
            v = row.get(key)
        return str(v or "").strip()

    parts = (
        _g("subject"),
        _g("sender"),
        _g("recipients"),
        _g("full_body_clean"),
        _g("top_reply_clean"),
        _g("body"),
    )
    return "\n".join(p for p in parts if p)


def _batch_hits_in_blob(blob: str, batch_norms: frozenset[str]) -> set[str]:
    """Return batch addresses that appear in ``blob`` with simple boundary guards."""
    if not blob or not batch_norms:
        return set()
    lower = blob.lower()
    hit: set[str] = set()
    for em in batch_norms:
        if not em:
            continue
        esc = re.escape(em)
        if re.search(rf"(?<![a-z0-9._%+-]){esc}(?![a-z0-9._+-])", lower, flags=re.I):
            hit.add(em)
    return hit


def _batch_hits_from_ndr_dsn(blob: str, batch_norms: frozenset[str]) -> set[str]:
    """Match batch emails only when parsed as failed RCPT from the NDR/DSN body.

    Avoids suppressing the visible To of a BCC campaign send when the NDR only
    reports failure for a BCC recipient quoted in the original message headers.
    """
    if not blob or not batch_norms:
        return set()
    failed = set(extract_failed_recipients_from_ndr(blob))
    hits = {em for em in failed if em in batch_norms}
    if hits:
        return hits
    # Fallback: single unambiguous batch mention in diagnostic text (legacy tests).
    in_blob = _batch_hits_in_blob(blob, batch_norms)
    if len(in_blob) == 1:
        return in_blob
    return set()


def classify_ndr_suppression_reason(blob: str) -> str:
    """``bounce_no_such_user`` when diagnostic text looks like unknown mailbox; else ``bounce_other``."""
    b = (blob or "").lower()
    if any(m in b for m in _NO_SUCH_USER_MARKERS):
        return "bounce_no_such_user"
    return "bounce_other"


def merge_suppression_reason(a: str, b: str) -> str:
    if a == "bounce_no_such_user" or b == "bounce_no_such_user":
        return "bounce_no_such_user"
    return "bounce_other"


@dataclass
class BounceBatchScanResult:
    batch: list[str]
    bad: dict[str, dict[str, object]] = field(default_factory=dict)
    evidence: list[dict[str, object]] = field(default_factory=list)

    @property
    def good(self) -> list[str]:
        bad_set = set(self.bad)
        return [e for e in self.batch if e not in bad_set]


def iter_recent_gmail_bounce_rows(
    conn: sqlite3.Connection,
    *,
    since_date: str,
    source_like: str = "gmail:%",
) -> Iterator[dict[str, object]]:
    cur = conn.execute(
        """
        SELECT id, source_file, sender, recipients, subject, body,
               full_body_clean, top_reply_clean, date_iso, date_raw
        FROM emails
        WHERE source_file LIKE ?
          AND date_iso IS NOT NULL
          AND length(trim(date_iso)) >= 10
          AND substr(date_iso, 1, 10) >= ?
        ORDER BY date_iso ASC
        """,
        (source_like, since_date[:10]),
    )
    desc = cur.description or ()
    names = [str(c[0]) for c in desc]
    for tup in cur:
        yield dict(zip(names, tup))


def scan_batch_against_ingested_bounces(
    conn: sqlite3.Connection,
    batch: list[str],
    *,
    since_days: int,
    source_like: str = "gmail:%",
) -> BounceBatchScanResult:
    batch_norms = frozenset(e.strip().lower() for e in batch if str(e).strip())
    since = cutoff_date_str(since_days=since_days)
    result = BounceBatchScanResult(batch=sorted(batch_norms))

    for row in iter_recent_gmail_bounce_rows(conn, since_date=since, source_like=source_like):
        blob = _ndr_blob_from_row(row)
        subj_l = str(row["subject"] or "").lower()
        body_l = blob.lower()
        cl = classify_email(
            sender=str(row["sender"] or ""),
            recipients=str(row["recipients"] or ""),
            subject=str(row["subject"] or ""),
            body=blob[:50000],
        )
        extra_bounce = any((x in subj_l) or (x in body_l) for x in _EXTRA_BOUNCE_SUBJECT_FRAGMENTS)
        if not cl.get("is_bounce") and not extra_bounce:
            continue
        hits = _batch_hits_from_ndr_dsn(blob, batch_norms)
        if not hits:
            continue
        reason = classify_ndr_suppression_reason(blob)
        eid = int(row["id"])
        result.evidence.append(
            {
                "email_id": eid,
                "source_file": row["source_file"],
                "date_iso": row["date_iso"],
                "subject": (row["subject"] or "")[:200],
                "matched_batch_emails": sorted(hits),
                "suppression_reason_code": reason,
            }
        )
        for em in hits:
            prev = result.bad.get(em)
            if prev is None:
                result.bad[em] = {
                    "suppression_reason_code": reason,
                    "evidence_email_ids": [eid],
                }
            else:
                prev["suppression_reason_code"] = merge_suppression_reason(
                    str(prev["suppression_reason_code"]),
                    reason,
                )
                ids = list(prev["evidence_email_ids"])
                if eid not in ids:
                    ids.append(eid)
                prev["evidence_email_ids"] = ids

    return result


def scan_batch_against_ingested_bounces_from_text(
    conn: sqlite3.Connection,
    batch_file_text: str,
    *,
    since_days: int,
    source_like: str = "gmail:%",
) -> BounceBatchScanResult:
    batch = load_batch_emails_from_file(batch_file_text)
    return scan_batch_against_ingested_bounces(
        conn, batch, since_days=since_days, source_like=source_like
    )


def format_scan_summary(r: BounceBatchScanResult) -> dict[str, object]:
    return {
        "batch_count": len(r.batch),
        "bad_count": len(r.bad),
        "good_count": len(r.good),
        "bad": {k: v for k, v in sorted(r.bad.items())},
        "good": r.good,
        "evidence_count": len(r.evidence),
    }


def apply_bounce_batch_scan(
    conn: sqlite3.Connection,
    scan: BounceBatchScanResult,
    *,
    updated_by: str,
    suppression_source: str,
    outreach_source: str,
    outreach_notes: str | None,
    mark_contacted_for_good: bool,
) -> dict[str, object]:
    """Write ``contact_email_suppression`` for NDR hits.

    Optionally set ``outreach_contact_state`` to ``contacted`` for addresses in the batch that
    were not matched to an NDR (only when ``mark_contacted_for_good`` is true).
    """
    from origenlab_email_pipeline.contact_email_suppression import (
        ensure_contact_email_suppression_table,
        upsert_contact_email_suppression,
        validate_contact_email_suppression_payload,
    )
    from origenlab_email_pipeline.outreach_contact_state import (
        ensure_outreach_contact_state_table,
        fetch_outreach_contact_state_row,
        outreach_touch_timestamps_for_upsert,
        upsert_outreach_contact_state,
        validate_outreach_contact_state_payload,
    )
    from origenlab_email_pipeline.timeutil import now_iso

    ts = now_iso()
    ensure_contact_email_suppression_table(conn)
    ensure_outreach_contact_state_table(conn)

    suppressed = 0
    for em, meta in sorted(scan.bad.items()):
        reason = str(meta["suppression_reason_code"])
        eids = meta.get("evidence_email_ids") or []
        note = f"NDR matched batch; evidence email_id={eids}"
        payload = validate_contact_email_suppression_payload(
            email=em,
            suppression_reason_code=reason,
            suppression_reason_text=note[:2000],
            suppression_source=suppression_source,
            last_bounced_at=ts[:10],
            updated_by=updated_by,
        )
        upsert_contact_email_suppression(conn, payload=payload, at_iso=ts)
        suppressed += 1

    contacted = 0
    if mark_contacted_for_good:
        for em in scan.good:
            existing = fetch_outreach_contact_state_row(conn, em)
            first, last = outreach_touch_timestamps_for_upsert(
                new_state="contacted",
                existing_row=existing,
                touch_at_iso=ts,
            )
            op_payload = validate_outreach_contact_state_payload(
                contact_email=em,
                state="contacted",
                first_contacted_at=first,
                last_contacted_at=last,
                source=outreach_source,
                notes=outreach_notes,
                updated_by=updated_by,
                lead_id=None,
            )
            upsert_outreach_contact_state(conn, payload=op_payload, at_iso=ts)
            contacted += 1

    return {"suppressed": suppressed, "marked_contacted": contacted, "at": ts}
