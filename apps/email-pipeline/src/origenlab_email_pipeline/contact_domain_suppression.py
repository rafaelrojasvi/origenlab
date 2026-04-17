"""Operator-owned email **domain** suppressions for cold outreach (SQLite sidecar).

Blocks every address on a listed registrable domain (and subdomains) via the shared export gate.
Use for orgs where any contact from that domain must never surface in marketing/archive exports.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from origenlab_email_pipeline.timeutil import now_iso

CONTACT_DOMAIN_SUPPRESSION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contact_domain_suppression (
  domain_norm TEXT PRIMARY KEY,
  suppression_reason_text TEXT,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
"""

_MAX_DOMAIN = 253
_MAX_REASON = 2000
_MAX_UPDATED_BY = 160


@dataclass(frozen=True)
class ContactDomainSuppressionPayload:
    domain_norm: str
    suppression_reason_text: str | None
    updated_by: str | None


def ensure_contact_domain_suppression_table(conn: sqlite3.Connection) -> None:
    conn.executescript(CONTACT_DOMAIN_SUPPRESSION_SCHEMA_SQL)


def contact_domain_suppression_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_domain_suppression'"
    ).fetchone()
    return bool(row)


def _trim(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    return s[:max_len]


def validate_contact_domain_suppression_payload(
    *,
    domain: str,
    suppression_reason_text: str | None,
    updated_by: str | None,
) -> ContactDomainSuppressionPayload:
    d = _trim(domain, _MAX_DOMAIN)
    if not d or "." not in d or "@" in d or " " in d:
        raise ValueError("Dominio no válido: use algo tipo ejemplo.cl (sin @, sin espacios).")
    return ContactDomainSuppressionPayload(
        domain_norm=d,
        suppression_reason_text=_trim(suppression_reason_text, _MAX_REASON),
        updated_by=_trim(updated_by, _MAX_UPDATED_BY),
    )


def load_suppressed_contact_domain_norms(conn: sqlite3.Connection) -> frozenset[str]:
    """Normalized domain strings for GateContext (empty if table missing)."""
    if not contact_domain_suppression_table_exists(conn):
        return frozenset()
    try:
        rows = conn.execute(
            """
            SELECT lower(trim(domain_norm)) AS d
            FROM contact_domain_suppression
            WHERE length(trim(domain_norm)) > 0
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return frozenset()
    out: set[str] = set()
    for (d,) in rows:
        if d:
            out.add(str(d))
    return frozenset(out)


def upsert_contact_domain_suppression(
    conn: sqlite3.Connection,
    *,
    payload: ContactDomainSuppressionPayload,
    at_iso: str | None = None,
) -> None:
    ts = at_iso or now_iso()
    conn.execute(
        """
        INSERT INTO contact_domain_suppression (
          domain_norm, suppression_reason_text, updated_at, updated_by
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(domain_norm) DO UPDATE SET
          suppression_reason_text = excluded.suppression_reason_text,
          updated_at = excluded.updated_at,
          updated_by = excluded.updated_by
        """,
        (
            payload.domain_norm,
            payload.suppression_reason_text,
            ts,
            payload.updated_by,
        ),
    )


__all__ = [
    "CONTACT_DOMAIN_SUPPRESSION_SCHEMA_SQL",
    "ContactDomainSuppressionPayload",
    "contact_domain_suppression_table_exists",
    "ensure_contact_domain_suppression_table",
    "load_suppressed_contact_domain_norms",
    "upsert_contact_domain_suppression",
    "validate_contact_domain_suppression_payload",
]
