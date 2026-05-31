"""Compare SQLite outbound sidecars with Postgres outbound.* mirror counts."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

BOUNCE_REASON_PREFIX = "bounce_"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _sqlite_count(conn: sqlite3.Connection, sql: str) -> int:
    if not conn:
        return 0
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


def sqlite_outbound_sidecar_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts for outbound sidecar tables in SQLite."""
    out: dict[str, int] = {
        "email_suppression_total": 0,
        "bounce_suppressions": 0,
        "domain_suppression_total": 0,
        "outreach_state_total": 0,
        "outreach_contacted": 0,
        "contacted_sidecar_distinct_emails": 0,
    }
    if _table_exists(conn, "contact_email_suppression"):
        out["email_suppression_total"] = _sqlite_count(
            conn, "SELECT COUNT(*) FROM contact_email_suppression"
        )
        out["bounce_suppressions"] = _sqlite_count(
            conn,
            f"""
            SELECT COUNT(*) FROM contact_email_suppression
            WHERE suppression_reason_code LIKE '{BOUNCE_REASON_PREFIX}%'
            """,
        )
    if _table_exists(conn, "contact_domain_suppression"):
        out["domain_suppression_total"] = _sqlite_count(
            conn, "SELECT COUNT(*) FROM contact_domain_suppression"
        )
    if _table_exists(conn, "outreach_contact_state"):
        out["outreach_state_total"] = _sqlite_count(
            conn, "SELECT COUNT(*) FROM outreach_contact_state"
        )
        out["outreach_contacted"] = _sqlite_count(
            conn,
            """
            SELECT COUNT(*) FROM outreach_contact_state
            WHERE LOWER(TRIM(state)) = 'contacted'
            """,
        )
    if _table_exists(conn, "contact_email_suppression") and _table_exists(
        conn, "outreach_contact_state"
    ):
        out["contacted_sidecar_distinct_emails"] = _sqlite_count(
            conn,
            """
            SELECT COUNT(*) FROM (
              SELECT LOWER(TRIM(email)) AS em FROM contact_email_suppression
              UNION
              SELECT LOWER(TRIM(contact_email_norm)) AS em
              FROM outreach_contact_state
              WHERE LOWER(TRIM(state)) IN ('contacted', 'replied', 'snoozed')
            )
            """,
        )
    elif _table_exists(conn, "contact_email_suppression"):
        out["contacted_sidecar_distinct_emails"] = out["email_suppression_total"]
    elif _table_exists(conn, "outreach_contact_state"):
        out["contacted_sidecar_distinct_emails"] = _sqlite_count(
            conn,
            """
            SELECT COUNT(DISTINCT LOWER(TRIM(contact_email_norm)))
            FROM outreach_contact_state
            WHERE LOWER(TRIM(state)) IN ('contacted', 'replied', 'snoozed')
            """,
        )
    return out


def sqlite_lead_research_segment_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Blocked and net-new-safe counts from SQLite lead_research_prospect."""
    if not _table_exists(conn, "lead_research_prospect"):
        return {"lead_blocked": 0, "lead_net_new_safe": 0}
    return {
        "lead_blocked": _sqlite_count(
            conn,
            """
            SELECT COUNT(*) FROM lead_research_prospect
            WHERE is_active = 1 AND is_blocked = 1
            """,
        ),
        "lead_net_new_safe": _sqlite_count(
            conn,
            """
            SELECT COUNT(*) FROM lead_research_prospect
            WHERE is_active = 1
              AND is_blocked = 0
              AND classification = 'net_new_safe_review'
            """,
        ),
    }


def count_contacted_exact_csv_rows(path: Path) -> int | None:
    """Count data rows in contacted_exact_emails_for_exclusion.csv (header excluded)."""
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def postgres_outbound_sidecar_counts(cur: Any) -> dict[str, int]:
    """Row counts for outbound sidecar tables in Postgres."""
    def _pg_count(sql: str) -> int:
        cur.execute(sql)
        row = cur.fetchone()
        return int(row[0]) if row else 0

    return {
        "email_suppression_total": _pg_count(
            "SELECT COUNT(*) FROM outbound.contact_email_suppression"
        ),
        "bounce_suppressions": _pg_count(
            f"""
            SELECT COUNT(*) FROM outbound.contact_email_suppression
            WHERE suppression_reason_code LIKE '{BOUNCE_REASON_PREFIX}%'
            """
        ),
        "domain_suppression_total": _pg_count(
            "SELECT COUNT(*) FROM outbound.contact_domain_suppression"
        ),
        "outreach_state_total": _pg_count(
            "SELECT COUNT(*) FROM outbound.outreach_contact_state"
        ),
        "outreach_contacted": _pg_count(
            """
            SELECT COUNT(*) FROM outbound.outreach_contact_state
            WHERE LOWER(TRIM(state)) = 'contacted'
            """
        ),
        "contacted_sidecar_distinct_emails": _pg_count(
            """
            SELECT COUNT(*) FROM (
              SELECT LOWER(TRIM(email)) AS em FROM outbound.contact_email_suppression
              UNION
              SELECT LOWER(TRIM(contact_email_norm)) AS em
              FROM outbound.outreach_contact_state
              WHERE LOWER(TRIM(state)) IN ('contacted', 'replied', 'snoozed')
            ) t
            """
        ),
    }


def postgres_lead_research_segment_counts(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'lead_intel' AND table_name = 'prospect'
        LIMIT 1
        """
    )
    if not cur.fetchone():
        return {"lead_blocked": 0, "lead_net_new_safe": 0}

    def _pg_count(sql: str) -> int:
        cur.execute(sql)
        row = cur.fetchone()
        return int(row[0]) if row else 0

    return {
        "lead_blocked": _pg_count(
            """
            SELECT COUNT(*) FROM lead_intel.prospect
            WHERE is_blocked IS TRUE
            """
        ),
        "lead_net_new_safe": _pg_count(
            """
            SELECT COUNT(*) FROM lead_intel.prospect
            WHERE is_blocked IS NOT TRUE
              AND classification = 'net_new_safe_review'
            """
        ),
    }


def compare_outbound_sidecar_mirror(
    sqlite_counts: dict[str, int],
    postgres_counts: dict[str, int],
    *,
    include_lead_research: bool = False,
    sqlite_lead: dict[str, int] | None = None,
    postgres_lead: dict[str, int] | None = None,
    contacted_exact_csv_count: int | None = None,
) -> dict[str, Any]:
    """Return verification report; ok=False when any mirrored count diverges."""
    errors: list[str] = []
    parity_keys = (
        "email_suppression_total",
        "bounce_suppressions",
        "domain_suppression_total",
        "outreach_state_total",
        "outreach_contacted",
        "contacted_sidecar_distinct_emails",
    )
    for key in parity_keys:
        s = sqlite_counts.get(key, 0)
        p = postgres_counts.get(key, 0)
        if s != p:
            errors.append(
                f"Postgres mirror stale: {key} sqlite={s} postgres={p}"
            )

    if include_lead_research:
        sqlite_lead = sqlite_lead or {}
        postgres_lead = postgres_lead or {}
        for key in ("lead_blocked", "lead_net_new_safe"):
            s = sqlite_lead.get(key, 0)
            p = postgres_lead.get(key, 0)
            if s != p:
                errors.append(
                    f"Postgres lead_intel mirror stale: {key} sqlite={s} postgres={p}"
                )

    report: dict[str, Any] = {
        "ok": not errors,
        "errors": errors,
        "sqlite_counts": sqlite_counts,
        "postgres_counts": postgres_counts,
    }
    if include_lead_research:
        report["sqlite_lead_segments"] = sqlite_lead
        report["postgres_lead_segments"] = postgres_lead
    if contacted_exact_csv_count is not None:
        report["contacted_exact_csv_rows"] = contacted_exact_csv_count
    return report
