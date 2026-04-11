"""Manual suppression / bounce tracking for contact emails used in review UIs.

Rows here are operator-owned and additive. They do not mutate ``emails`` or ``contact_master``.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.timeutil import now_iso

CONTACT_EMAIL_SUPPRESSION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contact_email_suppression (
  email TEXT PRIMARY KEY,
  suppression_reason_code TEXT NOT NULL,
  suppression_reason_text TEXT,
  suppression_source TEXT,
  last_bounced_at TEXT,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_contact_email_suppression_reason
  ON contact_email_suppression(suppression_reason_code);
"""

SUPPRESSION_REASON_CODES: tuple[str, ...] = (
    "bounce_no_such_user",
    "bounce_access_denied",
    "bounce_other",
    "manual_do_not_contact",
    "reported_non_delivery",
)

_MAX_EMAIL = 320
_MAX_REASON_TEXT = 2000
_MAX_SOURCE = 160
_MAX_UPDATED_BY = 160


@dataclass(frozen=True)
class ContactEmailSuppressionPayload:
    email: str
    suppression_reason_code: str
    suppression_reason_text: str | None
    suppression_source: str | None
    last_bounced_at: str | None
    updated_by: str | None


def streamlit_contact_suppression_rw_enabled() -> bool:
    return os.environ.get("ORIGENLAB_STREAMLIT_CONTACT_SUPPRESSION_RW") == "1"


def ensure_contact_email_suppression_table(conn: sqlite3.Connection) -> None:
    conn.executescript(CONTACT_EMAIL_SUPPRESSION_SCHEMA_SQL)


def contact_email_suppression_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_email_suppression'"
    ).fetchone()
    return bool(row)


def _trim(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def _valid_email(addr: str) -> bool:
    s = addr.strip().lower()
    found = emails_in(s)
    return bool(found) and found[0] == s


def validate_contact_email_suppression_payload(
    *,
    email: str,
    suppression_reason_code: str,
    suppression_reason_text: str | None,
    suppression_source: str | None,
    last_bounced_at: str | None,
    updated_by: str | None,
) -> ContactEmailSuppressionPayload:
    email_clean = _trim(email, _MAX_EMAIL)
    if not email_clean or not _valid_email(email_clean):
        raise ValueError("Correo no válido: use un email claro tipo nombre@dominio.cl")
    code = (suppression_reason_code or "").strip()
    if code not in SUPPRESSION_REASON_CODES:
        raise ValueError(
            f"Motivo no válido: {suppression_reason_code!r}. Use uno de: {', '.join(SUPPRESSION_REASON_CODES)}."
        )
    return ContactEmailSuppressionPayload(
        email=email_clean.lower(),
        suppression_reason_code=code,
        suppression_reason_text=_trim(suppression_reason_text, _MAX_REASON_TEXT),
        suppression_source=_trim(suppression_source, _MAX_SOURCE),
        last_bounced_at=_trim(last_bounced_at, 64),
        updated_by=_trim(updated_by, _MAX_UPDATED_BY),
    )


def fetch_contact_email_suppression_row(conn: sqlite3.Connection, email: str) -> dict[str, object] | None:
    try:
        row = conn.execute(
            """
            SELECT email, suppression_reason_code, suppression_reason_text, suppression_source,
                   last_bounced_at, updated_at, updated_by
            FROM contact_email_suppression
            WHERE lower(email) = lower(?)
            """,
            (str(email).strip().lower(),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    cols = (
        "email",
        "suppression_reason_code",
        "suppression_reason_text",
        "suppression_source",
        "last_bounced_at",
        "updated_at",
        "updated_by",
    )
    if isinstance(row, sqlite3.Row):
        return {c: row[c] for c in cols}
    return dict(zip(cols, row))


def fetch_contact_email_suppression_map(
    conn: sqlite3.Connection, emails: list[str] | tuple[str, ...]
) -> dict[str, dict[str, object]]:
    items = sorted({str(e).strip().lower() for e in emails if str(e).strip()})
    if not items:
        return {}
    try:
        placeholders = ",".join("?" for _ in items)
        rows = conn.execute(
            f"""
            SELECT email, suppression_reason_code, suppression_reason_text, suppression_source,
                   last_bounced_at, updated_at, updated_by
            FROM contact_email_suppression
            WHERE lower(email) IN ({placeholders})
            """,
            tuple(items),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        rec = fetch_contact_email_suppression_row(conn, row[0])
        if rec:
            out[str(rec["email"]).lower()] = rec
    return out


def upsert_contact_email_suppression(
    conn: sqlite3.Connection,
    *,
    payload: ContactEmailSuppressionPayload,
    at_iso: str | None = None,
) -> None:
    ts = at_iso or now_iso()
    conn.execute(
        """
        INSERT INTO contact_email_suppression (
          email, suppression_reason_code, suppression_reason_text, suppression_source,
          last_bounced_at, updated_at, updated_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          suppression_reason_code = excluded.suppression_reason_code,
          suppression_reason_text = excluded.suppression_reason_text,
          suppression_source = excluded.suppression_source,
          last_bounced_at = excluded.last_bounced_at,
          updated_at = excluded.updated_at,
          updated_by = excluded.updated_by
        """,
        (
            payload.email,
            payload.suppression_reason_code,
            payload.suppression_reason_text,
            payload.suppression_source,
            payload.last_bounced_at,
            ts,
            payload.updated_by,
        ),
    )


def delete_contact_email_suppression(conn: sqlite3.Connection, email: str) -> None:
    conn.execute("DELETE FROM contact_email_suppression WHERE lower(email) = lower(?)", (email.strip().lower(),))
