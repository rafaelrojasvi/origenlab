"""Manual contact research / enrichment for leads (operator-owned, not from raw import).

Rows live in ``lead_contact_research`` (1:1 with ``lead_master``). Imported fields on
``lead_master`` are never modified here.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.org_normalize import normalize_domain
from origenlab_email_pipeline.timeutil import now_iso

CONTACT_RESEARCH_STATUSES: tuple[str, ...] = (
    "nuevo",
    "investigar_contacto",
    "contacto_encontrado",
    "listo_para_contacto",
    "descartado",
)

_DEFAULT_STATUS = "nuevo"

_MAX_DOMAIN = 255
_MAX_NAME = 240
_MAX_EMAIL = 320
_MAX_NOTES = 8000
_MAX_SOURCE = 160
_MAX_UPDATED_BY = 160


@dataclass(frozen=True)
class ContactResearchPayload:
    contact_research_status: str
    resolved_domain: str | None
    resolved_contact_name: str | None
    resolved_contact_email: str | None
    contact_source: str | None
    contact_research_notes: str | None
    updated_by: str | None


_OPERATOR_LEADS_REVIEW_RW = "ORIGENLAB_OPERATOR_LEADS_REVIEW_RW"
_LEGACY_STREAMLIT_LEADS_REVIEW_RW = "ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW"


def _operator_env_flag_enabled(*, new_var: str, legacy_var: str) -> bool:
    if os.environ.get(new_var) is not None:
        return os.environ.get(new_var) == "1"
    return os.environ.get(legacy_var) == "1"


def operator_leads_review_rw_enabled() -> bool:
    """True when operator may write ``lead_contact_research`` (opt-in via env)."""
    return _operator_env_flag_enabled(
        new_var=_OPERATOR_LEADS_REVIEW_RW,
        legacy_var=_LEGACY_STREAMLIT_LEADS_REVIEW_RW,
    )


def streamlit_leads_review_rw_enabled() -> bool:
    """Deprecated alias for :func:`operator_leads_review_rw_enabled`."""
    return operator_leads_review_rw_enabled()


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


def validate_contact_research_payload(
    *,
    contact_research_status: str,
    resolved_domain: str | None,
    resolved_contact_name: str | None,
    resolved_contact_email: str | None,
    contact_source: str | None,
    contact_research_notes: str | None,
    updated_by: str | None,
) -> ContactResearchPayload:
    """Normalize and validate form fields; raises ``ValueError`` with a short message."""
    st = (contact_research_status or "").strip()
    if st not in CONTACT_RESEARCH_STATUSES:
        raise ValueError(
            f"Estado de investigación no válido: {contact_research_status!r}. "
            f"Use uno de: {', '.join(CONTACT_RESEARCH_STATUSES)}."
        )

    dom_raw = _trim(resolved_domain, _MAX_DOMAIN)
    dom_norm: str | None = None
    if dom_raw:
        dom_norm = normalize_domain(dom_raw)
        if not dom_norm:
            raise ValueError(
                "Dominio no utilizable: indique un hostname con punto (p.ej. institucion.gob.cl), sin basura."
            )

    name = _trim(resolved_contact_name, _MAX_NAME)
    email_raw = _trim(resolved_contact_email, _MAX_EMAIL)
    email_norm: str | None = None
    if email_raw:
        if not _valid_email(email_raw):
            raise ValueError("Correo no válido: use un formato claro tipo nombre@dominio.cl")
        email_norm = email_raw.strip().lower()

    src = _trim(contact_source, _MAX_SOURCE)
    notes = _trim(contact_research_notes, _MAX_NOTES)
    who = _trim(updated_by, _MAX_UPDATED_BY)

    if st == _DEFAULT_STATUS and not dom_norm and not name and not email_norm and not notes and not src:
        raise ValueError(
            "No hay nada que guardar: complete al menos dominio, contacto, correo, notas o un origen del dato."
        )

    return ContactResearchPayload(
        contact_research_status=st,
        resolved_domain=dom_norm,
        resolved_contact_name=name,
        resolved_contact_email=email_norm,
        contact_source=src,
        contact_research_notes=notes,
        updated_by=who,
    )


def fetch_contact_research_row(conn: sqlite3.Connection, lead_id: int) -> dict[str, object] | None:
    try:
        row = conn.execute(
            """
            SELECT lead_id, contact_research_status, resolved_domain, resolved_contact_name,
                   resolved_contact_email, contact_source, contact_research_notes, updated_at, updated_by
            FROM lead_contact_research
            WHERE lead_id = ?
            """,
            (int(lead_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        # Older DBs or RO viewer before DDL was applied; treat as no enrichment row.
        return None
    if row is None:
        return None
    cols = (
        "lead_id",
        "contact_research_status",
        "resolved_domain",
        "resolved_contact_name",
        "resolved_contact_email",
        "contact_source",
        "contact_research_notes",
        "updated_at",
        "updated_by",
    )
    if isinstance(row, sqlite3.Row):
        return {c: row[c] for c in cols}
    return dict(zip(cols, row))


def upsert_contact_research(
    conn: sqlite3.Connection,
    *,
    lead_id: int,
    payload: ContactResearchPayload,
    at_iso: str | None = None,
) -> None:
    """Insert or replace the enrichment row for ``lead_id`` (caller commits)."""
    ts = at_iso or now_iso()
    conn.execute(
        """
        INSERT INTO lead_contact_research (
          lead_id, contact_research_status, resolved_domain, resolved_contact_name,
          resolved_contact_email, contact_source, contact_research_notes, updated_at, updated_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lead_id) DO UPDATE SET
          contact_research_status = excluded.contact_research_status,
          resolved_domain = excluded.resolved_domain,
          resolved_contact_name = excluded.resolved_contact_name,
          resolved_contact_email = excluded.resolved_contact_email,
          contact_source = excluded.contact_source,
          contact_research_notes = excluded.contact_research_notes,
          updated_at = excluded.updated_at,
          updated_by = excluded.updated_by
        """,
        (
            int(lead_id),
            payload.contact_research_status,
            payload.resolved_domain,
            payload.resolved_contact_name,
            payload.resolved_contact_email,
            payload.contact_source,
            payload.contact_research_notes,
            ts,
            payload.updated_by,
        ),
    )


def delete_contact_research(conn: sqlite3.Connection, lead_id: int) -> None:
    """Remove enrichment row (operator reset)."""
    conn.execute("DELETE FROM lead_contact_research WHERE lead_id = ?", (int(lead_id),))


def archive_org_hint_for_domain(
    conn: sqlite3.Connection, normalized_domain: str
) -> tuple[str | None, int | None]:
    """If ``organization_master`` has this domain (case-insensitive), return (name_guess, total_emails)."""
    if not normalized_domain or not normalized_domain.strip():
        return None, None
    try:
        row = conn.execute(
            """
            SELECT organization_name_guess, total_emails
            FROM organization_master
            WHERE lower(domain) = lower(?)
            LIMIT 1
            """,
            (normalized_domain.strip(),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None, None
    if not row:
        return None, None
    return row[0], int(row[1]) if row[1] is not None else None
