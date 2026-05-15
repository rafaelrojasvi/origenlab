"""Operational (canonical Gmail) vs archive (full mart) scope for dashboards and API."""

from __future__ import annotations

from typing import Literal

from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE
from origenlab_email_pipeline.marketing_contact_noise import (
    marketing_outreach_noise_email,
    marketing_outreach_noise_organization_guess,
)

DataScope = Literal["canonical", "archive"]

CANONICAL_SCOPE_LABEL = "Gmail operativo (contacto@origenlab.cl)"
ARCHIVE_SCOPE_LABEL = "mart completo / histórico"

CANONICAL_SCOPE_NOTE = (
    "Solo filas ligadas a correo con "
    f"source_file LIKE '{CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE}' "
    "(excluye ruido operacional: mailer-daemon, rebotes, etc.)."
)

ARCHIVE_SCOPE_NOTE = (
    "Todo el mart reconstruido sobre el archivo completo (Labdelivery, PST, IMAP, etc.)."
)

CANONICAL_POSTGRES_UNAVAILABLE_NOTE = (
    "Canonical scope not available from current Postgres mirror; load canonical mart tables "
    "(mart.*_canonical) via sqlite_mart_core_to_postgres.py or use SQLite/Streamlit."
)

# Domains seen in archive mart that must not surface on operational Inicio / Qué hacer hoy.
_OPERATIONAL_BLOCKLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "postabg.delcon.it",
        "ussrdispatch.info",
        "delcon.it",
    }
)


def normalize_data_scope(scope: str | None) -> DataScope:
    s = (scope or "canonical").strip().lower()
    return "archive" if s == "archive" else "canonical"


def postgres_mart_relation(base_table: str, scope: DataScope) -> str:
    """``mart.contact_master`` or ``mart.contact_master_canonical``."""
    if scope == "archive":
        return f"mart.{base_table}"
    return f"mart.{base_table}_canonical"


def is_operational_noise_entity(entity_kind: str | None, entity_key: str | None) -> bool:
    """Exclude mailer-daemon, NOISE_SENDER, ESP noise from operational Inicio / hoy."""
    ek = (entity_key or "").strip()
    if not ek:
        return True
    low = ek.lower()
    if low in {"noise_sender", "no_reply", "noreply", "donotreply", "mailer-daemon", "postmaster"}:
        return True
    if "mailer-daemon" in low or "postmaster" in low or "mail delivery subsystem" in low:
        return True
    kind = (entity_kind or "").strip().lower()
    if kind == "contact" or "@" in low:
        return marketing_outreach_noise_email(low, strict_contact_graph=True)
    if kind == "organization" or ("." in low and "@" not in low):
        if low in _OPERATIONAL_BLOCKLIST_DOMAINS or any(
            low == d or low.endswith("." + d) for d in _OPERATIONAL_BLOCKLIST_DOMAINS
        ):
            return True
        return marketing_outreach_noise_organization_guess(low)
    return False


def sql_exclude_operational_noise_email(column: str) -> str:
    """Trusted SQL fragment (column must be a simple identifier path)."""
    c = f"lower(trim({column}))"
    return (
        f"({c} NOT LIKE '%mailer-daemon%' "
        f"AND {c} NOT LIKE '%postmaster%' "
        f"AND {c} NOT LIKE '%noise_sender%' "
        f"AND {c} NOT LIKE '%mail delivery subsystem%')"
    )


def sqlite_canonical_emails_predicate(table_alias: str = "e") -> str:
    col = f"{table_alias}.source_file"
    return f"lower({col}) LIKE '{CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE}'"


def sqlite_contact_canonical_link_exists(contact_alias: str = "cm") -> str:
    pred = sqlite_canonical_emails_predicate("e")
    email = f"lower(trim({contact_alias}.email))"
    return f"""
    EXISTS (
      SELECT 1 FROM emails e
      WHERE {pred}
        AND (
          lower(trim(e.sender)) = {email}
          OR lower(coalesce(e.recipients, '')) LIKE '%' || {email} || '%'
        )
    )
    """


def sqlite_organization_canonical_link_exists(org_alias: str = "om") -> str:
    pred = sqlite_canonical_emails_predicate("e")
    domain = f"lower(trim({org_alias}.domain))"
    noise = sql_exclude_operational_noise_email("cm.email")
    return f"""
    EXISTS (
      SELECT 1 FROM contact_master cm
      INNER JOIN emails e ON {pred}
        AND (
          lower(trim(e.sender)) = lower(trim(cm.email))
          OR lower(coalesce(e.recipients, '')) LIKE '%' || lower(trim(cm.email)) || '%'
        )
      WHERE lower(trim(cm.domain)) = {domain}
        AND {noise}
    )
    """


def sqlite_opportunity_signal_operational_predicate(signal_alias: str = "os") -> str:
    pred = sqlite_canonical_emails_predicate("e")
    ek = f"lower(trim({signal_alias}.entity_key))"
    noise = sql_exclude_operational_noise_email(f"{signal_alias}.entity_key")
    link_cm = sqlite_contact_canonical_link_exists("cm")
    link_om = sqlite_organization_canonical_link_exists("om")
    return f"""
    (
      ({signal_alias}.email_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM emails e
        WHERE e.id = {signal_alias}.email_id AND {pred}
      ))
      OR (
        {signal_alias}.entity_kind = 'contact'
        AND EXISTS (
          SELECT 1 FROM contact_master cm
          WHERE lower(trim(cm.email)) = {ek}
            AND {link_cm}
        )
      )
      OR (
        {signal_alias}.entity_kind = 'organization'
        AND EXISTS (
          SELECT 1 FROM organization_master om
          WHERE lower(trim(om.domain)) = {ek}
            AND {link_om}
        )
      )
    )
    AND {noise}
    """
