"""Mirror SQLite lead_research_* into Postgres lead_intel.* (read-only, redacted)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.lead_research.lead_research_mirror_read_model import (
    load_lead_research_mirror_payload,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import lead_research_tables_exist
from origenlab_email_pipeline.lead_research.lead_research_builder import sqlite_lead_research_counts
from origenlab_email_pipeline.mart_core_postgres_migrate import connect_sqlite_readonly

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

LEAD_INTEL_PG_TABLES: tuple[tuple[str, str], ...] = (
    ("lead_intel", "prospect"),
    ("lead_intel", "evidence"),
    ("lead_intel", "recommendation"),
    ("lead_intel", "block_reason"),
)

_DELETE_ORDER: tuple[tuple[str, str], ...] = tuple(reversed(LEAD_INTEL_PG_TABLES))


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            f"psycopg is required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


def pg_lead_intel_tables_exist(cur: Any) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'lead_intel' AND table_name = 'prospect'
        LIMIT 1
        """
    )
    return cur.fetchone() is not None


def postgres_lead_intel_counts(cur: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, table in LEAD_INTEL_PG_TABLES:
        cur.execute(f"SELECT COUNT(*) FROM lead_intel.{table}")
        row = cur.fetchone()
        out[table] = int(row[0]) if row else 0
    return out


def lead_research_mirror_built_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts after operational overlay — same payload sync writes to Postgres."""
    payload = load_lead_research_mirror_payload(conn)
    return {key: len(payload[key]) for key in payload}


# SQLite table counts use plural keys; Postgres mirror table names are singular.
_BUILT_TO_PG_COUNT_KEYS: tuple[tuple[str, str], ...] = (
    ("prospects", "prospect"),
    ("evidence", "evidence"),
    ("recommendations", "recommendation"),
    ("block_reasons", "block_reason"),
)


def lead_research_mirror_built_segment_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Blocked / net-new-safe counts from overlaid prospects (parity with lead_intel mirror)."""
    if not lead_research_tables_exist(conn):
        return {"lead_blocked": 0, "lead_net_new_safe": 0}
    prospects = load_lead_research_mirror_payload(conn)["prospects"]
    return {
        "lead_blocked": sum(1 for p in prospects if p.get("is_blocked")),
        "lead_net_new_safe": sum(
            1
            for p in prospects
            if not p.get("is_blocked") and p.get("classification") == "net_new_safe_review"
        ),
    }


def compare_lead_research_mirror_counts(
    built_counts: dict[str, int],
    pg_counts: dict[str, int],
) -> list[str]:
    """Return human-readable errors when Postgres row counts diverge from built mirror."""
    errors: list[str] = []
    for built_key, pg_key in _BUILT_TO_PG_COUNT_KEYS:
        built_n = int(built_counts.get(built_key) or 0)
        pg_n = int(pg_counts.get(pg_key) or 0)
        if built_n != pg_n:
            errors.append(
                f"{pg_key} count mismatch built={built_n} postgres={pg_n}"
            )
    return errors


def sync_lead_research_postgres_mirror(
    pg_url: str,
    sqlite_path: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    _require_psycopg()
    assert psycopg is not None

    conn = connect_sqlite_readonly(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        if not lead_research_tables_exist(conn):
            return {
                "dry_run": dry_run,
                "skipped": True,
                "reason": "sqlite_tables_missing",
                "sqlite_counts": sqlite_lead_research_counts(conn),
            }
        payload = load_lead_research_mirror_payload(conn)
        sqlite_counts = sqlite_lead_research_counts(conn)
    finally:
        conn.close()

    built = {k: len(payload[k]) for k in payload}
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "skipped": False,
        "sqlite_counts": sqlite_counts,
        "built_counts": built,
        "written_counts": {k: 0 for k in built},
    }
    if dry_run:
        result["skipped"] = True
        return result

    _require_psycopg()
    with psycopg.connect(pg_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:
            if not pg_lead_intel_tables_exist(cur):
                result["skipped"] = True
                result["reason"] = "table_missing"
                return result

    synced_at = datetime.now(timezone.utc)

    with psycopg.connect(pg_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:

            for schema, table in _DELETE_ORDER:
                cur.execute(f"DELETE FROM {schema}.{table}")

            for row in payload["prospects"]:
                cur.execute(
                    """
                    INSERT INTO lead_intel.prospect (
                      prospect_key, organization_name, contact_name, email, domain,
                      sector, region, buyer_type, likely_need, product_angle,
                      evidence_url, evidence_note, source, final_score, confidence,
                      classification, spanish_message_angle, risk_flags,
                      block_or_review_reason, recommended_next_action, status,
                      campaign_bucket, is_blocked, synced_at,
                      source_type, dataset_label,
                      gmail_first_contacted_at, gmail_last_contacted_at,
                      gmail_sent_count, gmail_received_count, gmail_latest_subject_safe
                    ) VALUES (
                      %(prospect_key)s, %(organization_name)s, %(contact_name)s, %(email)s,
                      %(domain)s, %(sector)s, %(region)s, %(buyer_type)s, %(likely_need)s,
                      %(product_angle)s, %(evidence_url)s, %(evidence_note)s, %(source)s,
                      %(final_score)s, %(confidence)s, %(classification)s,
                      %(spanish_message_angle)s, %(risk_flags)s, %(block_or_review_reason)s,
                      %(recommended_next_action)s, %(status)s, %(campaign_bucket)s,
                      %(is_blocked)s, %(synced_at)s,
                      %(source_type)s, %(dataset_label)s,
                      %(gmail_first_contacted_at)s, %(gmail_last_contacted_at)s,
                      %(gmail_sent_count)s, %(gmail_received_count)s, %(gmail_latest_subject_safe)s
                    )
                    """,
                    {**row, "synced_at": synced_at},
                )
            for row in payload["evidence"]:
                cur.execute(
                    """
                    INSERT INTO lead_intel.evidence (
                      prospect_key, evidence_kind, evidence_url, evidence_note, source, confidence, synced_at
                    ) VALUES (%(prospect_key)s, %(evidence_kind)s, %(evidence_url)s, %(evidence_note)s,
                              %(source)s, %(confidence)s, %(synced_at)s)
                    """,
                    {**row, "synced_at": synced_at},
                )
            for row in payload["recommendations"]:
                cur.execute(
                    """
                    INSERT INTO lead_intel.recommendation (
                      prospect_key, campaign_bucket, recommended_message_angle,
                      recommended_next_action, why_this_lead, suggested_subject,
                      suggested_body_preview, safety_note, synced_at
                    ) VALUES (
                      %(prospect_key)s, %(campaign_bucket)s, %(recommended_message_angle)s,
                      %(recommended_next_action)s, %(why_this_lead)s, %(suggested_subject)s,
                      %(suggested_body_preview)s, %(safety_note)s, %(synced_at)s
                    )
                    """,
                    {**row, "synced_at": synced_at},
                )
            for row in payload["block_reasons"]:
                cur.execute(
                    """
                    INSERT INTO lead_intel.block_reason (
                      prospect_key, reason_code, reason_label, synced_at
                    ) VALUES (%(prospect_key)s, %(reason_code)s, %(reason_label)s, %(synced_at)s)
                    """,
                    {**row, "synced_at": synced_at},
                )

            pg_conn.commit()
            result["written_counts"] = postgres_lead_intel_counts(cur)

    return result
