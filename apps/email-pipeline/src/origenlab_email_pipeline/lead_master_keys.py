"""Canonical (source_name, source_record_id) key helpers for lead_master.

Empty or whitespace-only external ids map to '' so they match UNIQUE enforcement
and ON CONFLICT upserts.

Read-only reporting (blank IDs, duplicate groups, per-source stats, samples):
`origenlab_email_pipeline.lead_master_audit` and `scripts/leads/audit_lead_master_duplicates.py`.
"""

from __future__ import annotations

import sqlite3

# SQL aligned with canonical_source_record_id() for plain lead_master vs alias `lm`.
CANONICAL_SOURCE_RECORD_ID_SQL = "COALESCE(NULLIF(TRIM(source_record_id), ''), '')"
CANONICAL_SOURCE_RECORD_ID_SQL_LM = "COALESCE(NULLIF(TRIM(lm.source_record_id), ''), '')"


def canonical_source_record_id(value: str | None) -> str:
    """Normalize source_record_id for storage and uniqueness (never NULL)."""
    if value is None:
        return ""
    s = str(value).strip()
    return s if s else ""


def backfill_canonical_source_record_ids(conn: sqlite3.Connection) -> int:
    """Set lead_master.source_record_id to canonical form for every row. Returns rows changed."""
    cur = conn.execute(
        """
        UPDATE lead_master
        SET source_record_id = COALESCE(NULLIF(TRIM(source_record_id), ''), '')
        WHERE source_record_id IS NULL
           OR source_record_id != COALESCE(NULLIF(TRIM(source_record_id), ''), '')
        """
    )
    conn.commit()
    return int(cur.rowcount if cur.rowcount is not None else 0)


def count_duplicate_key_groups(conn: sqlite3.Connection) -> int:
    """Number of (source_name, canonical source_record_id) groups with more than one row."""
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
          SELECT 1
          FROM lead_master
          GROUP BY source_name, {CANONICAL_SOURCE_RECORD_ID_SQL}
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()
    return int(row[0] if row else 0)


def list_duplicate_key_groups(conn: sqlite3.Connection) -> list[tuple[str, str, list[int]]]:
    """Each duplicate (source_name, canonical source_record_id) with all lead ids (no GROUP_CONCAT cap)."""
    rows = conn.execute(
        f"""
        WITH dup AS (
          SELECT source_name, {CANONICAL_SOURCE_RECORD_ID_SQL} AS sk
          FROM lead_master
          GROUP BY source_name, sk
          HAVING COUNT(*) > 1
        )
        SELECT lm.source_name,
               {CANONICAL_SOURCE_RECORD_ID_SQL_LM} AS sk,
               lm.id
        FROM lead_master AS lm
        INNER JOIN dup AS d
          ON d.source_name = lm.source_name
         AND d.sk = {CANONICAL_SOURCE_RECORD_ID_SQL_LM}
        ORDER BY lm.source_name, sk, lm.id
        """
    ).fetchall()
    grouped: dict[tuple[str, str], list[int]] = {}
    for sn, sk, lid in rows:
        grouped.setdefault((str(sn), str(sk)), []).append(int(lid))
    return [(sn, sk, ids) for (sn, sk), ids in sorted(grouped.items())]


def fetch_duplicate_groups(conn: sqlite3.Connection) -> list[tuple[str, str, int, str]]:
    """Return (source_name, canonical_key, count, comma-separated ids) for reporting."""
    out: list[tuple[str, str, int, str]] = []
    for sn, sk, ids in list_duplicate_key_groups(conn):
        out.append((sn, sk, len(ids), ",".join(str(i) for i in ids)))
    return out


def ensure_lead_master_source_unique_index(conn: sqlite3.Connection) -> None:
    """Create UNIQUE(source_name, source_record_id) after canonical backfill.

    Raises:
        RuntimeError: if duplicate keys remain or index cannot be created.
    """
    try:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uidx_lead_master_source_name_record
            ON lead_master(source_name, source_record_id)
            """
        )
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
        conn.rollback()
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            raise RuntimeError(
                "lead_master still has duplicate (source_name, source_record_id) "
                "after canonical backfill. Run:\n"
                "  uv run python scripts/leads/audit_lead_master_duplicates.py\n"
                "  uv run python scripts/leads/dedupe_lead_master.py --apply\n"
                f"Original error: {e}"
            ) from e
        raise
