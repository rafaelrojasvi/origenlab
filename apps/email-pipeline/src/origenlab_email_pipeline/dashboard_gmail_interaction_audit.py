"""Compact Gmail/SQLite interaction audit by domain (read-only dashboard snapshot)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import emails_in, primary_sender_email
from origenlab_email_pipeline.mart_core_postgres_migrate import connect_sqlite_readonly
from origenlab_email_pipeline.warm_case_grouping import normalize_subject_group_token
from origenlab_email_pipeline.warm_case_role_classification import _is_sent_folder
from origenlab_email_pipeline.warm_case_sender_rules import INTERNAL_OPERATOR_DOMAINS
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source

SCHEMA_VERSION = 1
DEFAULT_LOOKBACK_DAYS = 180
SOURCE_LABEL = "sqlite:gmail:contacto"

DOMAIN_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "ika.net.br": ("ika.net.br", "ika.com", "ika.de"),
    "serva.de": ("serva.de", "serva-electrophoresis.com"),
    "ortoalresa.com": ("ortoalresa.com", "alvarezredondo.com"),
}

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in DOMAIN_ALIAS_GROUPS.items():
    _ALIAS_TO_CANONICAL[_canonical] = _canonical
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias] = _canonical


def canonical_audit_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    return _ALIAS_TO_CANONICAL.get(d, d)


def matched_aliases_for_canonical(canonical: str) -> list[str]:
    aliases = DOMAIN_ALIAS_GROUPS.get(canonical)
    if aliases:
        return list(aliases)
    return [canonical]


def is_internal_audit_domain(domain: str) -> bool:
    d = (domain or "").strip().lower()
    if not d:
        return True
    if d in INTERNAL_OPERATOR_DOMAINS:
        return True
    for internal in INTERNAL_OPERATOR_DOMAINS:
        if d == internal or d.endswith(f".{internal}"):
            return True
    return False


def safe_subject_line(subject: str | None, *, max_len: int = 120) -> str:
    text = (subject or "").strip().replace("\n", " ").replace("\r", " ")
    if not text:
        return ""
    return text[:max_len]


def _is_sent_message(
    folder: str | None,
    source_file: str | None,
    sender: str | None,
) -> bool:
    if _is_sent_folder(source_file):
        return True
    f = (folder or "").lower()
    if "enviad" in f or "sent mail" in f or f.endswith("/sent"):
        return True
    sender_email = primary_sender_email(sender or "")
    if sender_email and "@" in sender_email:
        sender_domain = sender_email.split("@", 1)[1].lower()
        if not is_internal_audit_domain(sender_domain):
            return False
        return True
    return False


def _thread_group_key(subject: str, domain: str) -> str:
    token = normalize_subject_group_token(subject)
    return f"subject:{domain}|{token}"


@dataclass
class _DomainAccum:
    message_count: int = 0
    sent_count: int = 0
    received_count: int = 0
    thread_keys: set[str] = field(default_factory=set)
    latest_email_at: str | None = None
    latest_subject_safe: str = ""
    has_attachments: bool = False
    matched_aliases: set[str] = field(default_factory=set)


def _accumulate_rows(
    accum: dict[str, _DomainAccum],
    rows: list[tuple[Any, ...]],
) -> None:
    for row in rows:
        _id, source_file, folder, _message_id, sender, recipients, date_iso, subject, has_att = row
        raw_domains: set[str] = set()
        for email in emails_in(f"{sender or ''} {recipients or ''}"):
            domain = email.split("@", 1)[-1].lower()
            if not is_internal_audit_domain(domain):
                raw_domains.add(domain)
        if not raw_domains:
            continue

        is_sent = _is_sent_message(folder, source_file, sender)
        subject_safe = safe_subject_line(subject)

        for raw_domain in raw_domains:
            canonical = canonical_audit_domain(raw_domain)
            bucket = accum.setdefault(canonical, _DomainAccum())
            bucket.message_count += 1
            if is_sent:
                bucket.sent_count += 1
            else:
                bucket.received_count += 1
            bucket.matched_aliases.add(raw_domain)
            bucket.thread_keys.add(_thread_group_key(subject or "", canonical))
            if has_att:
                bucket.has_attachments = True
            if bucket.latest_email_at is None or (date_iso or "") >= bucket.latest_email_at:
                bucket.latest_email_at = date_iso
                bucket.latest_subject_safe = subject_safe


def build_gmail_interaction_audit_snapshot(
    sqlite_path: Path,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Build compact per-domain Gmail interaction counts from read-only SQLite."""
    now_dt = now or datetime.now(timezone.utc)
    generated_at = now_dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    cutoff = (now_dt - timedelta(days=lookback_days)).isoformat()

    predicate = sql_predicate_contacto_gmail_source()
    query = f"""
        SELECT id, source_file, folder, message_id, sender, recipients,
               date_iso, subject, has_attachments
        FROM emails
        WHERE {predicate}
          AND date_iso IS NOT NULL
          AND date_iso >= ?
        ORDER BY date_iso ASC
    """

    accum: dict[str, _DomainAccum] = {}
    own_conn = conn is None
    db = conn
    if own_conn:
        db = connect_sqlite_readonly(sqlite_path)
    assert db is not None
    try:
        rows = db.execute(query, (cutoff,)).fetchall()
        _accumulate_rows(accum, rows)
    finally:
        if own_conn:
            db.close()

    domains_list: list[dict[str, Any]] = []
    for domain in sorted(accum.keys()):
        bucket = accum[domain]
        domains_list.append(
            {
                "domain": domain,
                "message_count": bucket.message_count,
                "sent_count": bucket.sent_count,
                "received_count": bucket.received_count,
                "thread_count": len(bucket.thread_keys),
                "latest_email_at": bucket.latest_email_at,
                "latest_subject_safe": bucket.latest_subject_safe,
                "has_attachments": bucket.has_attachments,
                "matched_aliases": sorted(bucket.matched_aliases),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "source": SOURCE_LABEL,
        "lookback_days": lookback_days,
        "domains": domains_list,
    }


def find_audit_domain_row(
    snapshot: dict[str, Any],
    *,
    domain: str | None = None,
    domains: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    """Lookup a domain row by canonical name or alias list."""
    candidates = {canonical_audit_domain(domain)} if domain else set()
    if domains:
        candidates.update(canonical_audit_domain(d) for d in domains if d)
    if not candidates:
        return None
    for row in snapshot.get("domains") or []:
        row_domain = canonical_audit_domain(str(row.get("domain") or ""))
        if row_domain in candidates:
            return row
        aliases = row.get("matched_aliases") or []
        if any(canonical_audit_domain(str(a)) in candidates for a in aliases):
            return row
    return None
