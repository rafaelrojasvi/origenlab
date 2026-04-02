"""Durable contact-level outreach state (operator sidecar).

Rows do not mutate ``emails``, ``attachments``, or ``attachment_extracts``.
Hard exclusions (bounces, do-not-contact) stay in ``contact_email_suppression``.

Operational note: canonical **customer-facing contact / outreach** identity is **OrigenLab**
(``contacto@origenlab.cl``, ``@origenlab.cl``), including Gmail rows with
``source_file`` like ``gmail:contacto@origenlab.cl%``. **LabDelivery** (``labdelivery.cl``)
is a distinct domain in this repo; do not treat LabDelivery senders as the same
mailbox when inferring “we contacted them” from the archive—filter on OrigenLab
when adding derived logic or exports.

``lead_id`` optionally ties a row to ``lead_master.id`` when the lead pipeline is in use.
It is stored as a plain INTEGER (no FOREIGN KEY) so this table can be created on
email-only databases that do not yet have ``lead_master``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.timeutil import now_iso

OUTREACH_CONTACT_STATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS outreach_contact_state (
  contact_email_norm TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  first_contacted_at TEXT,
  last_contacted_at TEXT,
  source TEXT,
  notes TEXT,
  updated_at TEXT NOT NULL,
  updated_by TEXT,
  lead_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_outreach_contact_state_state
  ON outreach_contact_state(state);
CREATE INDEX IF NOT EXISTS idx_outreach_contact_state_lead_id
  ON outreach_contact_state(lead_id)
  WHERE lead_id IS NOT NULL;
"""

OUTREACH_STATES: tuple[str, ...] = (
    "not_contacted",
    "contacted",
    "replied",
    "snoozed",
)

_MAX_EMAIL = 320
_MAX_NOTES = 4000
_MAX_SOURCE = 160
_MAX_UPDATED_BY = 160


@dataclass(frozen=True)
class OutreachContactStatePayload:
    contact_email_norm: str
    state: str
    first_contacted_at: str | None
    last_contacted_at: str | None
    source: str | None
    notes: str | None
    updated_by: str | None
    lead_id: int | None


def ensure_outreach_contact_state_table(conn: sqlite3.Connection) -> None:
    conn.executescript(OUTREACH_CONTACT_STATE_SCHEMA_SQL)


def outreach_contact_state_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='outreach_contact_state'"
    ).fetchone()
    return bool(row)


def _trim(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def normalize_contact_email_for_outreach(email: str) -> str:
    """Trim, lowercase, and return a single-address mailbox string.

    Raises:
        ValueError: if the string does not parse to exactly one plausible email.
    """
    s = _trim(email, _MAX_EMAIL)
    if not s:
        raise ValueError("Correo no válido: use un email claro tipo nombre@dominio.cl")
    lowered = s.lower()
    found = emails_in(lowered)
    if not found or found[0] != lowered:
        raise ValueError("Correo no válido: use un email claro tipo nombre@dominio.cl")
    return lowered


def validate_outreach_contact_state_payload(
    *,
    contact_email: str,
    state: str,
    first_contacted_at: str | None = None,
    last_contacted_at: str | None = None,
    source: str | None = None,
    notes: str | None = None,
    updated_by: str | None = None,
    lead_id: int | None = None,
) -> OutreachContactStatePayload:
    norm = normalize_contact_email_for_outreach(contact_email)
    st = (state or "").strip().lower()
    if st not in OUTREACH_STATES:
        raise ValueError(
            f"Estado no válido: {state!r}. Use uno de: {', '.join(OUTREACH_STATES)}."
        )
    if lead_id is not None:
        if isinstance(lead_id, bool) or not isinstance(lead_id, int) or lead_id < 1:
            raise ValueError("lead_id debe ser un entero positivo o None")
    return OutreachContactStatePayload(
        contact_email_norm=norm,
        state=st,
        first_contacted_at=_trim(first_contacted_at, 64),
        last_contacted_at=_trim(last_contacted_at, 64),
        source=_trim(source, _MAX_SOURCE),
        notes=_trim(notes, _MAX_NOTES),
        updated_by=_trim(updated_by, _MAX_UPDATED_BY),
        lead_id=lead_id,
    )


def fetch_outreach_contact_state_row(
    conn: sqlite3.Connection, contact_email: str
) -> dict[str, object] | None:
    try:
        key = normalize_contact_email_for_outreach(contact_email)
    except ValueError:
        return None
    try:
        row = conn.execute(
            """
            SELECT contact_email_norm, state, first_contacted_at, last_contacted_at,
                   source, notes, updated_at, updated_by, lead_id
            FROM outreach_contact_state
            WHERE contact_email_norm = ?
            """,
            (key,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    cols = (
        "contact_email_norm",
        "state",
        "first_contacted_at",
        "last_contacted_at",
        "source",
        "notes",
        "updated_at",
        "updated_by",
        "lead_id",
    )
    if isinstance(row, sqlite3.Row):
        return {c: row[c] for c in cols}
    return dict(zip(cols, row))


def upsert_outreach_contact_state(
    conn: sqlite3.Connection,
    *,
    payload: OutreachContactStatePayload,
    at_iso: str | None = None,
) -> None:
    ts = at_iso or now_iso()
    conn.execute(
        """
        INSERT INTO outreach_contact_state (
          contact_email_norm, state, first_contacted_at, last_contacted_at,
          source, notes, updated_at, updated_by, lead_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_email_norm) DO UPDATE SET
          state = excluded.state,
          first_contacted_at = excluded.first_contacted_at,
          last_contacted_at = excluded.last_contacted_at,
          source = excluded.source,
          notes = excluded.notes,
          updated_at = excluded.updated_at,
          updated_by = excluded.updated_by,
          lead_id = excluded.lead_id
        """,
        (
            payload.contact_email_norm,
            payload.state,
            payload.first_contacted_at,
            payload.last_contacted_at,
            payload.source,
            payload.notes,
            ts,
            payload.updated_by,
            payload.lead_id,
        ),
    )
