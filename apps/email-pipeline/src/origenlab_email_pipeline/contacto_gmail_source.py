"""Canonical SQL and source-tier classification for contacto@origenlab.cl Gmail Workspace ingest.

Operational intelligence (dashboard/API read models, outbound readiness, case queues) treats rows whose
``source_file`` begins with ``gmail:contacto@origenlab.cl/`` as the **canonical** live mailbox.

Legacy ``contacto@labdelivery.cl`` mbox exports remain in ``emails`` for historical reference;
:classify_email_source: labels them ``legacy_labdelivery`` so callers can exclude them from
operational metrics without deleting data.
"""

from __future__ import annotations

from typing import Literal

# --- Canonical Workspace Gmail (live operational mailbox) ----------------------------

CONTACTO_GMAIL_SOURCE_PREFIX = "gmail:contacto@origenlab.cl/"
# Value used inside SQL ``LIKE`` (lower(source_file) LIKE …); must stay aligned with ingest.
CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE = "gmail:contacto@origenlab.cl/%"
# SQL LIKE operand (quoted), shared by all predicates below.
CONTACTO_GMAIL_LIKE = f"LIKE '{CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE}'"

# --- Legacy historical mailbox (PST/mbox exports; not operational truth) ------------

LEGACY_LABDELIVERY_SOURCE_LIKE = "%contacto@labdelivery%"

EmailSourceTier = Literal[
    "canonical_gmail",
    "legacy_labdelivery",
    "other_gmail",
    "imap",
    "mbox",
    "unknown",
]


def classify_email_source(source_file: str | None) -> EmailSourceTier:
    """Classify ``emails.source_file`` for operational vs historical reporting.

    ``canonical_gmail`` matches the Workspace ingest prefix only (must include ``/`` after
    the mailbox address to avoid accidental collision with unrelated ``gmail:`` strings).
    """
    if source_file is None:
        return "unknown"
    s = str(source_file).strip()
    if not s:
        return "unknown"
    sl = s.lower()
    if sl.startswith(CONTACTO_GMAIL_SOURCE_PREFIX.lower()):
        return "canonical_gmail"
    if "contacto@labdelivery" in sl:
        return "legacy_labdelivery"
    if sl.startswith("imap:"):
        return "imap"
    if sl.startswith("gmail:"):
        return "other_gmail"
    # Typical readpst / filesystem mbox paths (not imap:/gmail: virtual paths).
    if "/" in s or "\\" in s:
        return "mbox"
    return "unknown"


def is_canonical_contacto_gmail_source(source_file: str | None) -> bool:
    return classify_email_source(source_file) == "canonical_gmail"


def sql_predicate_contacto_gmail_source(
    *,
    table_alias: str | None = None,
    coalesce_null: bool = False,
) -> str:
    """Return ``lower(...) {CONTACTO_GMAIL_LIKE}`` for use in WHERE clauses.

    ``coalesce_null=True`` matches legacy forms that treat NULL ``source_file`` as empty string
    (e.g. ``cases_review_queue``). ``coalesce_null=False`` matches ``lower(source_file)`` forms
    used elsewhere (NULL still does not match the LIKE).
    """
    col = "source_file" if table_alias is None else f"{table_alias}.source_file"
    expr = f"lower(COALESCE({col}, ''))" if coalesce_null else f"lower({col})"
    return f"{expr} {CONTACTO_GMAIL_LIKE}"


def canonical_contacto_where_clause(
    *,
    table_alias: str | None = None,
    coalesce_null: bool = False,
) -> str:
    """SQL WHERE fragment for canonical Workspace Gmail rows (alias of :func:`sql_predicate_contacto_gmail_source`)."""
    return sql_predicate_contacto_gmail_source(table_alias=table_alias, coalesce_null=coalesce_null)


# Public alias for modules that referenced the unqualified-column + COALESCE form.
CONTACTO_GMAIL_SOURCE_SQL = sql_predicate_contacto_gmail_source(coalesce_null=True)
