"""Shared SQL for ``contact_master`` cold-export / audit candidate selection.

Same predicates and ordering as ``export_marketing_from_contact_master`` and
``export_candidate_audit`` (contact path). Scripts pass ``LIMIT`` as the sole bound.
"""

from __future__ import annotations

# Shared: table filter + rank order (must stay aligned across export vs audit).
_CONTACT_MASTER_MARKETING_FROM_WHERE_ORDER = """
FROM contact_master
WHERE email IS NOT NULL
  AND trim(email) != ''
  AND instr(email, '@') > 0
ORDER BY COALESCE(total_emails, 0) DESC, COALESCE(last_seen_at, '') DESC
LIMIT ?
""".strip()


def sql_contact_master_marketing_export_candidates() -> str:
    """Rows for ``export_marketing_from_contact_master`` (full mart fields for CSV)."""
    return f"""
SELECT
  lower(trim(email)) AS contact_email,
  COALESCE(contact_name_best, '') AS recipient_name,
  COALESCE(organization_name_guess, '') AS institution_name,
  COALESCE(total_emails, 0) AS total_emails,
  COALESCE(last_seen_at, '') AS last_seen_at,
  COALESCE(confidence_score, 0) AS confidence_score
{_CONTACT_MASTER_MARKETING_FROM_WHERE_ORDER}
""".strip()


def sql_contact_master_candidate_audit_contacts() -> str:
    """Subset of columns for ``export_candidate_audit`` contact_master branch."""
    return f"""
SELECT
  lower(trim(email)) AS contact_email,
  COALESCE(organization_name_guess, '') AS institution_name,
  '' AS fit_bucket,
  NULL AS id_lead
{_CONTACT_MASTER_MARKETING_FROM_WHERE_ORDER}
""".strip()


# Stable column lists for tests / callers (SQLite cursor.description order).
CONTACT_MASTER_MARKETING_EXPORT_COLUMN_NAMES: tuple[str, ...] = (
    "contact_email",
    "recipient_name",
    "institution_name",
    "total_emails",
    "last_seen_at",
    "confidence_score",
)

CONTACT_MASTER_CANDIDATE_AUDIT_COLUMN_NAMES: tuple[str, ...] = (
    "contact_email",
    "institution_name",
    "fit_bucket",
    "id_lead",
)
