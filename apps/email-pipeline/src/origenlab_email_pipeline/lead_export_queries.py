"""Shared SQL fragments for lead exports and client reporting.

Single source for:
- upstream-active predicate on ``lead_master`` (re-exported from ``lead_upstream_reconcile``)
- deterministic ``best org match per lead`` (lowest ``lead_matches_existing_orgs.id`` per ``lead_id``)

Scripts should build only SELECT lists and WHERE/ORDER BY; join shape lives here.
"""

from __future__ import annotations

from typing import Literal

from origenlab_email_pipeline.lead_upstream_reconcile import sql_upstream_active

_BestOrgVariant = Literal["archive_only", "org_and_archive", "org_domain_archive"]

_SELECT_BY_VARIANT: dict[_BestOrgVariant, str] = {
    "archive_only": "m1.lead_id, m1.already_in_archive_flag",
    "org_and_archive": "m1.lead_id, m1.matched_org_name, m1.already_in_archive_flag",
    "org_domain_archive": (
        "m1.lead_id, m1.matched_org_name, m1.matched_domain, m1.already_in_archive_flag"
    ),
}

_WHERE_MIN_ID = """m1.id = (
    SELECT MIN(m2.id) FROM lead_matches_existing_orgs m2 WHERE m2.lead_id = m1.lead_id
  )"""


def sql_upstream_active_lead_master(alias: str = "lm") -> str:
    """Predicate: ``lead_master`` row counts as upstream-active (not soft-retired)."""
    return sql_upstream_active(alias)


def sql_left_join_best_org_match(
    alias_lm: str = "lm",
    alias_m: str = "m",
    *,
    variant: _BestOrgVariant = "org_and_archive",
) -> str:
    """``LEFT JOIN (...) AS m ON m.lead_id = lm.id`` using one match row per lead (min id)."""
    cols = _SELECT_BY_VARIANT[variant]
    return (
        f"LEFT JOIN (\n"
        f"          SELECT {cols}\n"
        f"          FROM lead_matches_existing_orgs m1\n"
        f"          WHERE {_WHERE_MIN_ID}\n"
        f"        ) {alias_m} ON {alias_m}.lead_id = {alias_lm}.id"
    )


def sql_cte_best_org_match(
    cte_name: str = "best_match",
    *,
    variant: _BestOrgVariant = "org_domain_archive",
) -> str:
    """CTE fragment ``name AS ( SELECT ... )`` for use after ``WITH`` (e.g. client review export)."""
    cols = _SELECT_BY_VARIANT[variant]
    return (
        f"{cte_name} AS (\n"
        f"          SELECT {cols}\n"
        f"          FROM lead_matches_existing_orgs m1\n"
        f"          WHERE {_WHERE_MIN_ID}\n"
        f"        )"
    )
