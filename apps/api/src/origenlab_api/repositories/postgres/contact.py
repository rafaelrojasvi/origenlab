"""Postgres contact intelligence (``api.v_contact_profile`` + outbound fallback)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from origenlab_email_pipeline.outreach_contact_state import normalize_contact_email_for_outreach

from origenlab_api.repositories.contact import _domain_from_email, _is_domain_suppressed
from origenlab_api.repositories.contact_types import ContactQueryResult
from origenlab_api.repositories.postgres.common import postgres_connection, require_psycopg
from origenlab_api.settings import Settings

_BLOCKING_OUTREACH_STATES = frozenset({"contacted", "replied", "snoozed"})

_PROFILE_SQL = """
SELECT
  email_norm,
  email_display,
  contact_name,
  domain,
  organization_name,
  organization_domain,
  first_seen_at,
  last_seen_at,
  message_count,
  outreach_state,
  last_contacted_at,
  outreach_source,
  outreach_updated_by,
  outreach_notes,
  suppressed_email,
  suppressed_domain,
  do_not_repeat,
  sent_count,
  latest_sent_at,
  latest_subject,
  mart_present
FROM api.v_contact_profile
WHERE email_norm = %(email)s
LIMIT 1
"""

_OUTREACH_SQL = """
SELECT
  state,
  last_contacted_at,
  source,
  updated_by,
  notes
FROM outbound.outreach_contact_state
WHERE contact_email_norm = %(email)s
LIMIT 1
"""

_EMAIL_SUPPRESSION_SQL = """
SELECT 1
FROM outbound.contact_email_suppression
WHERE lower(trim(email)) = %(email)s
LIMIT 1
"""

_DOMAIN_SUPPRESSION_SQL = """
SELECT domain_norm
FROM outbound.contact_domain_suppression
"""


def map_profile_row(
    row: dict[str, Any],
    *,
    email_raw: str,
    email_norm: str,
    domain: str,
) -> ContactQueryResult:
    warnings: list[str] = []
    if not row.get("mart_present"):
        warnings.append("No contact_master row for this email.")

    contact = {
        "email": email_raw.strip(),
        "normalized_email": email_norm,
        "name": _str_field(row.get("contact_name")),
        "domain": _str_field(row.get("domain")) or domain,
        "organization_name": _str_field(row.get("organization_name")),
        "organization_domain": _str_field(row.get("organization_domain")) or domain,
        "last_seen_at": _format_ts(row.get("last_seen_at")),
        "first_seen_at": _format_ts(row.get("first_seen_at")),
        "message_count": _int_field(row.get("message_count")),
    }

    suppressed_email = bool(row.get("suppressed_email"))
    suppressed_domain = bool(row.get("suppressed_domain"))
    state = _optional_str(row.get("outreach_state"))
    sent_count = _int_field(row.get("sent_count"))

    do_not_repeat = bool(row.get("do_not_repeat"))
    if not do_not_repeat and state in _BLOCKING_OUTREACH_STATES:
        do_not_repeat = True
    if not do_not_repeat and sent_count > 0:
        do_not_repeat = True
    if suppressed_email or suppressed_domain:
        do_not_repeat = True

    outreach = {
        "state": state,
        "last_contacted_at": _format_ts(row.get("last_contacted_at")),
        "source": _str_field(row.get("outreach_source")),
        "updated_by": _str_field(row.get("outreach_updated_by")),
        "notes": _str_field(row.get("outreach_notes")),
        "do_not_repeat": do_not_repeat,
        "suppressed_email": suppressed_email,
        "suppressed_domain": suppressed_domain,
    }

    sent_history = {
        "sent_count": sent_count,
        "latest_sent_at": _format_ts(row.get("latest_sent_at")),
        "latest_subject": _optional_str(row.get("latest_subject")),
    }

    return ContactQueryResult(
        contact=contact,
        outreach=outreach,
        sent_history=sent_history,
        warnings=warnings,
        reduced_mode=False,
        data_source="postgres_mirror",
    )


def build_fallback_result(
    *,
    email_raw: str,
    email_norm: str,
    domain: str,
    outreach_row: dict[str, Any] | None,
    suppressed_email: bool,
    suppressed_domain: bool,
) -> ContactQueryResult:
    warnings = ["No contact_master row for this email."]
    if outreach_row is None:
        warnings.append(
            "No outreach_contact_state row (defaults to not_contacted semantics)."
        )

    state = _optional_str(outreach_row.get("state")) if outreach_row else None
    sent_history = _empty_sent_history()
    do_not_repeat = False
    if state in _BLOCKING_OUTREACH_STATES:
        do_not_repeat = True
    if suppressed_email or suppressed_domain:
        do_not_repeat = True

    outreach = {
        "state": state,
        "last_contacted_at": _format_ts(outreach_row.get("last_contacted_at"))
        if outreach_row
        else None,
        "source": _str_field(outreach_row.get("source")) if outreach_row else "",
        "updated_by": _str_field(outreach_row.get("updated_by")) if outreach_row else "",
        "notes": _str_field(outreach_row.get("notes")) if outreach_row else "",
        "do_not_repeat": do_not_repeat,
        "suppressed_email": suppressed_email,
        "suppressed_domain": suppressed_domain,
    }

    return ContactQueryResult(
        contact=_empty_contact(email_raw, email_norm, domain),
        outreach=outreach,
        sent_history=sent_history,
        warnings=warnings,
        reduced_mode=False,
        data_source="postgres_mirror",
    )


class PostgresContactRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_contact_detail(self, email_raw: str) -> ContactQueryResult:
        email_norm = normalize_contact_email_for_outreach(email_raw)
        domain = _domain_from_email(email_norm)
        require_psycopg()
        pg = require_psycopg()

        with postgres_connection(self._settings) as conn:
            with conn.cursor(row_factory=pg.rows.dict_row) as cur:
                cur.execute(_PROFILE_SQL, {"email": email_norm})
                profile = cur.fetchone()
                if profile is not None:
                    return map_profile_row(
                        dict(profile),
                        email_raw=email_raw,
                        email_norm=email_norm,
                        domain=domain,
                    )

                cur.execute(_OUTREACH_SQL, {"email": email_norm})
                outreach_row = cur.fetchone()
                outreach_dict = dict(outreach_row) if outreach_row else None

                cur.execute(_EMAIL_SUPPRESSION_SQL, {"email": email_norm})
                suppressed_email = cur.fetchone() is not None

                cur.execute(_DOMAIN_SUPPRESSION_SQL)
                domain_rows = [str(r["domain_norm"]) for r in cur.fetchall()]
                suppressed_domains = frozenset(d.lower().strip() for d in domain_rows if d)
                suppressed_domain = _is_domain_suppressed(domain, suppressed_domains)

        return build_fallback_result(
            email_raw=email_raw,
            email_norm=email_norm,
            domain=domain,
            outreach_row=outreach_dict,
            suppressed_email=suppressed_email,
            suppressed_domain=suppressed_domain,
        )


def _empty_contact(email_raw: str, email_norm: str, domain: str) -> dict[str, Any]:
    return {
        "email": email_raw.strip(),
        "normalized_email": email_norm,
        "name": "",
        "domain": domain,
        "organization_name": "",
        "organization_domain": domain,
        "last_seen_at": None,
        "first_seen_at": None,
        "message_count": 0,
    }


def _empty_sent_history() -> dict[str, Any]:
    return {"sent_count": 0, "latest_sent_at": None, "latest_subject": None}


def _str_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_field(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _format_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone().replace(microsecond=0).isoformat()
    text = str(value).strip()
    return text or None
