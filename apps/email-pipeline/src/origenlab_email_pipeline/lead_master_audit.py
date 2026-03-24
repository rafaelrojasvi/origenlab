"""Read-only lead_master source-key audit (duplicates, blank canonical IDs, weak signals)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import sqlite3

from origenlab_email_pipeline.lead_master_keys import (
    CANONICAL_SOURCE_RECORD_ID_SQL,
    CANONICAL_SOURCE_RECORD_ID_SQL_LM,
    count_duplicate_key_groups,
    fetch_duplicate_groups,
)


@dataclass
class SourceIdentityRow:
    """Per-source identity health (read-only audit)."""

    source_name: str
    total_leads: int
    blank_canonical_count: int
    duplicate_key_groups: int
    duplicate_surplus_rows: int
    suspect_short_numeric_ids: int

    @property
    def pct_blank(self) -> float:
        if self.total_leads <= 0:
            return 0.0
        return 100.0 * self.blank_canonical_count / self.total_leads

    def high_risk(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if self.blank_canonical_count > 0:
            reasons.append("has_blank_canonical_source_record_id")
        if self.duplicate_key_groups > 0:
            reasons.append("has_duplicate_key_groups")
        if self.duplicate_surplus_rows >= 5:
            reasons.append("many_rows_in_duplicate_keys")
        if self.source_name == "chilecompra" and self.suspect_short_numeric_ids >= 3:
            reasons.append("chilecompra_many_short_numeric_ids_check_row_index_fallback")
        if self.total_leads >= 10 and self.pct_blank >= 10.0:
            reasons.append("high_fraction_blank_canonical_ids")
        return bool(reasons), reasons


@dataclass
class LeadMasterIdentityAudit:
    """Snapshot for formatting / tests."""

    db_path: Path
    total_leads: int
    total_blank_canonical: int
    global_duplicate_groups: int
    sources: list[SourceIdentityRow] = field(default_factory=list)
    duplicate_group_details: list[tuple[str, str, int, str]] = field(default_factory=list)


def count_blank_canonical_leads(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM lead_master
        WHERE {CANONICAL_SOURCE_RECORD_ID_SQL} = ''
        """
    ).fetchone()
    return int(row[0] if row else 0)


def count_total_leads(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM lead_master").fetchone()
    return int(row[0] if row else 0)


def _per_source_base_stats(conn: sqlite3.Connection) -> list[SourceIdentityRow]:
    """One row per source_name with totals, blanks, short-digit heuristic."""
    rows = conn.execute(
        f"""
        SELECT
          source_name,
          COUNT(*) AS total,
          SUM(CASE WHEN {CANONICAL_SOURCE_RECORD_ID_SQL} = '' THEN 1 ELSE 0 END) AS blanks,
          SUM(
            CASE
              WHEN TRIM(COALESCE(source_record_id, '')) GLOB '[0-9]'
                OR TRIM(COALESCE(source_record_id, '')) GLOB '[0-9][0-9]'
                OR TRIM(COALESCE(source_record_id, '')) GLOB '[0-9][0-9][0-9]'
              THEN 1
              ELSE 0
            END
          ) AS short_num
        FROM lead_master
        GROUP BY source_name
        ORDER BY source_name
        """
    ).fetchall()
    out: list[SourceIdentityRow] = []
    for sn, total, blanks, short_num in rows:
        out.append(
            SourceIdentityRow(
                source_name=str(sn),
                total_leads=int(total or 0),
                blank_canonical_count=int(blanks or 0),
                duplicate_key_groups=0,
                duplicate_surplus_rows=0,
                suspect_short_numeric_ids=int(short_num or 0),
            )
        )
    return out


def _duplicate_stats_by_source(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    """source_name -> (duplicate_groups, surplus_rows sum(n-1))."""
    rows = conn.execute(
        f"""
        WITH g AS (
          SELECT source_name, {CANONICAL_SOURCE_RECORD_ID_SQL} AS sk, COUNT(*) AS n
          FROM lead_master
          GROUP BY source_name, sk
          HAVING COUNT(*) > 1
        )
        SELECT source_name, COUNT(*) AS grps, COALESCE(SUM(n - 1), 0) AS surplus
        FROM g
        GROUP BY source_name
        """
    ).fetchall()
    return {str(r[0]): (int(r[1]), int(r[2])) for r in rows}


def collect_lead_master_identity_audit(conn: sqlite3.Connection, db_path: Path) -> LeadMasterIdentityAudit:
    total = count_total_leads(conn)
    blank_total = count_blank_canonical_leads(conn)
    dup_groups = count_duplicate_key_groups(conn)
    base = _per_source_base_stats(conn)
    dup_by_src = _duplicate_stats_by_source(conn)
    merged: list[SourceIdentityRow] = []
    for row in base:
        grps, surplus = dup_by_src.get(row.source_name, (0, 0))
        merged.append(
            SourceIdentityRow(
                source_name=row.source_name,
                total_leads=row.total_leads,
                blank_canonical_count=row.blank_canonical_count,
                duplicate_key_groups=grps,
                duplicate_surplus_rows=surplus,
                suspect_short_numeric_ids=row.suspect_short_numeric_ids,
            )
        )
    dups = fetch_duplicate_groups(conn)
    return LeadMasterIdentityAudit(
        db_path=db_path.resolve(),
        total_leads=total,
        total_blank_canonical=blank_total,
        global_duplicate_groups=dup_groups,
        sources=merged,
        duplicate_group_details=dups,
    )


def sample_blank_rows(
    conn: sqlite3.Connection,
    *,
    source_name: str | None,
    limit: int,
) -> list[tuple[int, str, str, str, str | None, str | None]]:
    """id, source_name, raw source_record_id, canonical, org_name, source_url."""
    lim = max(1, min(limit, 20))
    if source_name is not None:
        rows = conn.execute(
            f"""
            SELECT id, source_name, source_record_id,
                   {CANONICAL_SOURCE_RECORD_ID_SQL} AS canonical_sk,
                   org_name, source_url
            FROM lead_master
            WHERE source_name = ?
              AND {CANONICAL_SOURCE_RECORD_ID_SQL} = ''
            ORDER BY id
            LIMIT ?
            """,
            (source_name, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT id, source_name, source_record_id,
                   {CANONICAL_SOURCE_RECORD_ID_SQL} AS canonical_sk,
                   org_name, source_url
            FROM lead_master
            WHERE {CANONICAL_SOURCE_RECORD_ID_SQL} = ''
            ORDER BY source_name, id
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    out: list[tuple[int, str, str, str, str | None, str | None]] = []
    for r in rows:
        out.append(
            (
                int(r[0]),
                str(r[1]),
                str(r[2]) if r[2] is not None else "",
                str(r[3]),
                r[4],
                r[5],
            )
        )
    return out


def sample_duplicate_rows(
    conn: sqlite3.Connection,
    *,
    source_name: str,
    limit: int,
) -> list[tuple[int, str, str, str, str | None, str | None]]:
    lim = max(1, min(limit, 20))
    rows = conn.execute(
        f"""
        SELECT lm.id, lm.source_name, lm.source_record_id,
               {CANONICAL_SOURCE_RECORD_ID_SQL_LM} AS canonical_sk,
               lm.org_name, lm.source_url
        FROM lead_master AS lm
        INNER JOIN (
          SELECT source_name, {CANONICAL_SOURCE_RECORD_ID_SQL} AS sk
          FROM lead_master
          GROUP BY source_name, sk
          HAVING COUNT(*) > 1
        ) AS d
          ON d.source_name = lm.source_name
         AND d.sk = {CANONICAL_SOURCE_RECORD_ID_SQL_LM}
        WHERE lm.source_name = ?
        ORDER BY canonical_sk, lm.id
        LIMIT ?
        """,
        (source_name, lim),
    ).fetchall()
    out: list[tuple[int, str, str, str, str | None, str | None]] = []
    for r in rows:
        out.append(
            (
                int(r[0]),
                str(r[1]),
                str(r[2]) if r[2] is not None else "",
                str(r[3]),
                r[4],
                r[5],
            )
        )
    return out


def format_audit_report_lines(
    audit: LeadMasterIdentityAudit,
    *,
    sample_limit: int,
    conn: sqlite3.Connection,
) -> list[str]:
    """Human-readable sections: summary, warnings, per-source, duplicate detail, samples."""
    lines: list[str] = []
    canon = CANONICAL_SOURCE_RECORD_ID_SQL
    lines.append("=== lead_master source-key audit (read-only) ===")
    lines.append(f"Database: {audit.db_path}")
    lines.append(f"Canonical key expression: {canon}")
    lines.append("")
    lines.append("--- SUMMARY ---")
    lines.append(f"Total lead_master rows: {audit.total_leads}")
    lines.append(
        f"Rows with blank canonical source_record_id: {audit.total_blank_canonical} "
        f"({100.0 * audit.total_blank_canonical / audit.total_leads:.1f}% of all)"
        if audit.total_leads
        else "Rows with blank canonical source_record_id: 0 (empty table)"
    )
    dup_fail = audit.global_duplicate_groups > 0
    lines.append(f"Duplicate key groups (source_name + canonical source_record_id): {audit.global_duplicate_groups}")
    lines.append(
        "With --fail-on-duplicates: exit 1 iff duplicate key groups > 0 "
        f"(this snapshot: {'would exit 1' if dup_fail else 'would exit 0'})."
    )
    lines.append("")

    warn_lines: list[str] = []
    for s in audit.sources:
        hr, reasons = s.high_risk()
        if hr:
            warn_lines.append(
                f"  [{s.source_name}] high_risk={'yes'} reasons={','.join(reasons)} "
                f"(total={s.total_leads} blank={s.blank_canonical_count} "
                f"dup_groups={s.duplicate_key_groups} dup_surplus_rows={s.duplicate_surplus_rows} "
                f"short_numeric_ids_1to3digits={s.suspect_short_numeric_ids})"
            )
    lines.append("--- WARNINGS ---")
    lines.append("  Advisory by default; blanks / weak-identity rows below do not change exit code.")
    lines.append("  With --fail-on-duplicates: duplicate key groups → exit 1. Missing DB path → exit 2 (no report).")
    if warn_lines:
        lines.extend(warn_lines)
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("--- PER-SOURCE IDENTITY ---")
    lines.append(
        "source_name | total | blank | %blank | dup_grps | dup_surplus | short_num_ids | high_risk"
    )
    for s in audit.sources:
        hr, _ = s.high_risk()
        lines.append(
            f"{s.source_name} | {s.total_leads} | {s.blank_canonical_count} | "
            f"{s.pct_blank:.1f}% | {s.duplicate_key_groups} | {s.duplicate_surplus_rows} | "
            f"{s.suspect_short_numeric_ids} | {'yes' if hr else 'no'}"
        )
    lines.append("")
    lines.append(
        "short_num_ids: raw source_record_id is digits-only, length 1–3 "
        "(possible fetch row-index fallback for chilecompra — see fetch_chilecompra.py)."
    )
    lines.append("")

    if audit.duplicate_group_details:
        lines.append("--- DUPLICATE KEY GROUPS (detail) ---")
        for sn, sk, cnt, ids_csv in audit.duplicate_group_details:
            lines.append(f"  source_name={sn!r} canonical_id={sk!r} count={cnt} lead_ids={ids_csv}")
        lines.append(
            "  Merge: uv run python scripts/leads/dedupe_lead_master.py --apply "
            "(survivor = min(id with lead_outreach_enrichment) if any else min(id))."
        )
        lines.append("")
    else:
        lines.append("--- DUPLICATE KEY GROUPS (detail) ---")
        lines.append("  (none)")
        lines.append("")

    lines.append("--- SAMPLES: blank canonical source_record_id ---")
    if audit.total_blank_canonical:
        affected = [s.source_name for s in audit.sources if s.blank_canonical_count]
        for sn in affected[:5]:
            lines.append(f"  source={sn!r} (up to {sample_limit} rows)")
            for tup in sample_blank_rows(conn, source_name=sn, limit=sample_limit):
                lid, src, raw, can, org, url = tup
                org_s = (org or "")[:60]
                url_s = (url or "")[:80]
                lines.append(
                    f"    id={lid} source_name={src!r} source_record_id_raw={raw!r} "
                    f"canonical={can!r} org_name={org_s!r} source_url={url_s!r}"
                )
        if len(affected) > 5:
            lines.append(f"  … {len(affected) - 5} more source(s) with blanks (omitted)")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("--- SAMPLES: duplicate keys ---")
    if audit.global_duplicate_groups:
        dup_sources = sorted({s.source_name for s in audit.sources if s.duplicate_key_groups})
        for sn in dup_sources[:5]:
            lines.append(f"  source={sn!r} (up to {sample_limit} rows from duplicate groups)")
            for tup in sample_duplicate_rows(conn, source_name=sn, limit=sample_limit):
                lid, src, raw, can, org, url = tup
                org_s = (org or "")[:60]
                url_s = (url or "")[:80]
                lines.append(
                    f"    id={lid} source_name={src!r} source_record_id_raw={raw!r} "
                    f"canonical={can!r} org_name={org_s!r} source_url={url_s!r}"
                )
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("--- CHILECOMPRA NOTE ---")
    lines.append(
        "If many source_record_id values are small integers (0,1,2,…) or short digit strings, "
        "check fetch_chilecompra.py: it falls back to the file row index when Codigo/Correlativo/etc. "
        "are missing — reordering the file changes IDs."
    )
    return lines
