"""Merge duplicate lead_master rows that share (source_name, canonical source_record_id).

Repoints lead_outreach_enrichment, mart match tables, and lead_account_membership before
deleting duplicate lead rows. Recreates uidx_lead_master_source_name_record when done.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from origenlab_email_pipeline.lead_master_keys import (
    backfill_canonical_source_record_ids,
    ensure_lead_master_source_unique_index,
    list_duplicate_key_groups,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base


@dataclass(frozen=True)
class DedupeStats:
    groups_merged: int
    leads_deleted: int
    enrichment_repointed: int
    enrichment_dropped: int


def _enriched_ids(conn: sqlite3.Connection, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT lead_id FROM lead_outreach_enrichment WHERE lead_id IN ({ph})",
        ids,
    ).fetchall()
    return {int(r[0]) for r in rows}


def _pick_survivor(conn: sqlite3.Connection, ids: list[int]) -> int:
    enr = _enriched_ids(conn, ids)
    if enr:
        return min(enr)
    return min(ids)


def _repoint_enrichment(
    conn: sqlite3.Connection, survivor: int, loser: int
) -> tuple[int, int]:
    """Returns (repointed_increment, dropped_increment)."""
    has_loser = conn.execute(
        "SELECT 1 FROM lead_outreach_enrichment WHERE lead_id = ?",
        (loser,),
    ).fetchone()
    if not has_loser:
        return (0, 0)
    has_survivor = conn.execute(
        "SELECT 1 FROM lead_outreach_enrichment WHERE lead_id = ?",
        (survivor,),
    ).fetchone()
    if has_survivor:
        conn.execute("DELETE FROM lead_outreach_enrichment WHERE lead_id = ?", (loser,))
        return (0, 1)
    conn.execute(
        "UPDATE lead_outreach_enrichment SET lead_id = ? WHERE lead_id = ?",
        (survivor, loser),
    )
    return (1, 0)


def _repoint_memberships(conn: sqlite3.Connection, survivor: int, loser: int) -> None:
    rows = conn.execute(
        "SELECT lead_account_id FROM lead_account_membership WHERE lead_id = ?",
        (loser,),
    ).fetchall()
    for (aid,) in rows:
        aid = int(aid)
        clash = conn.execute(
            """
            SELECT 1 FROM lead_account_membership
            WHERE lead_id = ? AND lead_account_id = ?
            """,
            (survivor, aid),
        ).fetchone()
        if clash:
            conn.execute(
                "DELETE FROM lead_account_membership WHERE lead_id = ? AND lead_account_id = ?",
                (loser, aid),
            )
        else:
            conn.execute(
                """
                UPDATE lead_account_membership SET lead_id = ?
                WHERE lead_id = ? AND lead_account_id = ?
                """,
                (survivor, loser, aid),
            )


def _dedupe_match_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM lead_matches_existing_orgs
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     PARTITION BY lead_id, matched_domain, match_type
                     ORDER BY id
                   ) AS rn
            FROM lead_matches_existing_orgs
          ) WHERE rn > 1
        )
        """
    )
    conn.execute(
        """
        DELETE FROM lead_matches_existing_contacts
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     PARTITION BY lead_id, matched_contact_email, match_type
                     ORDER BY id
                   ) AS rn
            FROM lead_matches_existing_contacts
          ) WHERE rn > 1
        )
        """
    )


def apply_lead_master_dedupe(conn: sqlite3.Connection) -> DedupeStats:
    """Merge duplicate keys, repoint dependents, recreate unique index. Commits on success."""
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_leads_tables_ddl_base(conn)
    backfill_canonical_source_record_ids(conn)

    groups = list_duplicate_key_groups(conn)
    if not groups:
        ensure_lead_master_source_unique_index(conn)
        return DedupeStats(0, 0, 0, 0)

    conn.execute("DROP INDEX IF EXISTS uidx_lead_master_source_name_record")
    conn.commit()

    groups_merged = 0
    leads_deleted = 0
    enrichment_repointed = 0
    enrichment_dropped = 0

    conn.execute("BEGIN")
    try:
        for _sn, _sk, ids in groups:
            if len(ids) < 2:
                continue
            survivor = _pick_survivor(conn, ids)
            losers = [i for i in ids if i != survivor]
            for loser in losers:
                rp, dr = _repoint_enrichment(conn, survivor, loser)
                enrichment_repointed += rp
                enrichment_dropped += dr
                conn.execute(
                    "UPDATE lead_matches_existing_orgs SET lead_id = ? WHERE lead_id = ?",
                    (survivor, loser),
                )
                conn.execute(
                    "UPDATE lead_matches_existing_contacts SET lead_id = ? WHERE lead_id = ?",
                    (survivor, loser),
                )
                if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_account_membership'"
                ).fetchone():
                    _repoint_memberships(conn, survivor, loser)
                conn.execute("DELETE FROM lead_master WHERE id = ?", (loser,))
                leads_deleted += 1
            groups_merged += 1

        _dedupe_match_tables(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    backfill_canonical_source_record_ids(conn)
    ensure_lead_master_source_unique_index(conn)

    return DedupeStats(
        groups_merged=groups_merged,
        leads_deleted=leads_deleted,
        enrichment_repointed=enrichment_repointed,
        enrichment_dropped=enrichment_dropped,
    )
