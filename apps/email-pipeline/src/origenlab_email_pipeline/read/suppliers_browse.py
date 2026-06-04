"""Read-only supplier browse for imported supplier / sourcing rows (extracted read module)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd
from pandas.errors import DatabaseError as PandasDatabaseError


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def supplier_browse_ready(conn: sqlite3.Connection) -> tuple[bool, str | None]:
    if not _table_exists(conn, "supplier_master"):
        return False, "missing_supplier_master"
    return True, None


def latest_import_batch_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MAX(id) FROM supplier_import_batch").fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


@dataclass(frozen=True)
class SupplierBrowseFilters:
    regions: tuple[str, ...] | None = None
    tiers: tuple[str, ...] | None = None
    min_confidence: float | None = None
    category_substring: str | None = None
    has_evidence: str = "any"  # any | yes | no
    has_channel: str = "any"  # any | yes | no
    statuses: tuple[str, ...] | None = None
    seen_in_mailbox: str = "any"  # any | yes | no
    exclude_exclusions: bool = False
    limit: int = 2000


def _validate_filter_token(value: str, allowed: frozenset[str]) -> str:
    v = (value or "any").strip().lower()
    return v if v in allowed else "any"


def supplier_browse_filter_options(conn: sqlite3.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"region": [], "tier": [], "status": []}
    ok, _ = supplier_browse_ready(conn)
    if not ok:
        return out
    bid = latest_import_batch_id(conn)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT TRIM(region_label) AS v FROM supplier_master
            WHERE region_label IS NOT NULL AND TRIM(region_label) != ''
            ORDER BY 1 LIMIT 400
            """
        ).fetchall()
        out["region"] = [str(r[0]) for r in rows if r[0]]
        if bid is not None:
            rows = conn.execute(
                """
                SELECT DISTINCT TRIM(tier) FROM supplier_priority_snapshot
                WHERE batch_id = ? AND tier IS NOT NULL AND TRIM(tier) != ''
                ORDER BY 1
                """,
                (bid,),
            ).fetchall()
            out["tier"] = [str(r[0]) for r in rows if r[0]]
        rows = conn.execute(
            """
            SELECT DISTINCT TRIM(status) FROM supplier_review_state
            WHERE status IS NOT NULL AND TRIM(status) != ''
            ORDER BY 1
            """
        ).fetchall()
        out["status"] = [str(r[0]) for r in rows if r[0]]
    except sqlite3.Error:
        pass
    return out


def build_suppliers_browse_sql(
    flt: SupplierBrowseFilters,
    *,
    include_mailbox_join: bool,
) -> tuple[str, list[object]]:
    """Parameterized SQL for supplier browse."""
    has_evidence = _validate_filter_token(flt.has_evidence, frozenset({"any", "yes", "no"}))
    has_channel = _validate_filter_token(flt.has_channel, frozenset({"any", "yes", "no"}))
    seen_mb = _validate_filter_token(flt.seen_in_mailbox, frozenset({"any", "yes", "no"}))

    if include_mailbox_join:
        om_join = "LEFT JOIN organization_master om ON om.domain = sm.domain_norm"
        om_select = "CASE WHEN om.domain IS NOT NULL THEN 1 ELSE 0 END AS seen_in_mailbox"
    else:
        om_join = ""
        om_select = "0 AS seen_in_mailbox"

    # Fixed query shape (batch snapshot); tier ordering via CASE (top15 > top50 > anexo > exclusion).
    sql = f"""
    SELECT
      sm.id AS supplier_id,
      sm.domain_norm,
      sm.trade_name,
      sm.region_label,
      sm.country_label,
      sm.equipment_focus,
      sm.is_exclusion,
      sps.tier,
      sps.rank_in_list,
      sps.confidence_score,
      sps.confidence_label,
      COALESCE(srs.status, 'nuevo') AS review_status,
      (SELECT COUNT(*) FROM supplier_evidence se WHERE se.supplier_id = sm.id) AS evidence_count,
      (SELECT se.url FROM supplier_evidence se WHERE se.supplier_id = sm.id ORDER BY se.id LIMIT 1) AS evidence_sample_url,
      (SELECT scc.channel_type || ': ' || scc.value_raw
       FROM supplier_contact_channel scc
       WHERE scc.supplier_id = sm.id
       ORDER BY scc.is_preferred DESC, scc.id
       LIMIT 1) AS primary_channel,
      (SELECT COUNT(*) FROM supplier_contact_channel scc WHERE scc.supplier_id = sm.id) AS channel_count,
      {om_select}
    FROM supplier_master sm
    LEFT JOIN supplier_priority_snapshot sps
      ON sps.supplier_id = sm.id
      AND sps.batch_id = (SELECT MAX(id) FROM supplier_import_batch)
    LEFT JOIN supplier_review_state srs ON srs.supplier_id = sm.id
    {om_join}
    WHERE 1 = 1
    """
    args: list[object] = []

    if flt.exclude_exclusions:
        sql += " AND COALESCE(sm.is_exclusion, 0) = 0"

    if flt.regions:
        sql += " AND sm.region_label IN (" + ",".join("?" for _ in flt.regions) + ")"
        args.extend(flt.regions)

    if flt.tiers:
        sql += " AND sps.tier IN (" + ",".join("?" for _ in flt.tiers) + ")"
        args.extend(flt.tiers)

    if flt.min_confidence is not None:
        sql += " AND sps.confidence_score >= ?"
        args.append(flt.min_confidence)

    if flt.category_substring and flt.category_substring.strip():
        sql += " AND COALESCE(sm.equipment_focus, '') LIKE ?"
        args.append(f"%{flt.category_substring.strip()}%")

    if has_evidence == "yes":
        sql += " AND EXISTS (SELECT 1 FROM supplier_evidence se WHERE se.supplier_id = sm.id)"
    elif has_evidence == "no":
        sql += " AND NOT EXISTS (SELECT 1 FROM supplier_evidence se WHERE se.supplier_id = sm.id)"

    if has_channel == "yes":
        sql += " AND EXISTS (SELECT 1 FROM supplier_contact_channel scc WHERE scc.supplier_id = sm.id)"
    elif has_channel == "no":
        sql += " AND NOT EXISTS (SELECT 1 FROM supplier_contact_channel scc WHERE scc.supplier_id = sm.id)"

    if flt.statuses:
        sql += " AND COALESCE(srs.status, 'nuevo') IN (" + ",".join("?" for _ in flt.statuses) + ")"
        args.extend(flt.statuses)

    if include_mailbox_join:
        if seen_mb == "yes":
            sql += " AND om.domain IS NOT NULL"
        elif seen_mb == "no":
            sql += " AND om.domain IS NULL"

    sql += """ ORDER BY
      CASE sps.tier
        WHEN 'top15' THEN 3
        WHEN 'top50' THEN 2
        WHEN 'anexo' THEN 1
        WHEN 'exclusion' THEN 0
        ELSE -1
      END DESC,
      COALESCE(sps.rank_in_list, 999999) ASC,
      sm.domain_norm
      LIMIT ?"""
    args.append(flt.limit)
    return sql, args


def fetch_suppliers_browse_df(
    conn: sqlite3.Connection,
    flt: SupplierBrowseFilters | None = None,
    *,
    include_mailbox_join: bool = True,
) -> pd.DataFrame:
    ok, _ = supplier_browse_ready(conn)
    if not ok:
        return pd.DataFrame()
    flt = flt or SupplierBrowseFilters()
    sql, args = build_suppliers_browse_sql(
        flt,
        include_mailbox_join=include_mailbox_join and _table_exists(conn, "organization_master"),
    )
    try:
        return pd.read_sql_query(sql, conn, params=args)
    except (sqlite3.Error, ValueError, PandasDatabaseError):
        return pd.DataFrame()
