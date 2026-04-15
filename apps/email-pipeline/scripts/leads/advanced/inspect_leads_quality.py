#!/usr/bin/env python3
"""Quick QA/inspection for lead pipeline quality (counts, top leads, tag coverage)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.leads_schema import ensure_leads_tables


def _print_kv(k: str, v: object) -> None:
    print(f"{k:28} {v}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect lead pipeline quality")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--top", type=int, default=15, help="Top N leads to print")
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)

    total = conn.execute("SELECT COUNT(*) FROM lead_master").fetchone()[0]
    by_source = conn.execute("SELECT source_name, COUNT(*) FROM lead_master GROUP BY source_name ORDER BY COUNT(*) DESC").fetchall()
    by_fit = conn.execute("SELECT COALESCE(fit_bucket,'(null)'), COUNT(*) FROM lead_master GROUP BY COALESCE(fit_bucket,'(null)')").fetchall()
    with_eq = conn.execute(
        "SELECT COUNT(*) FROM lead_master WHERE equipment_match_tags IS NOT NULL AND length(trim(equipment_match_tags))>0"
    ).fetchone()[0]
    with_lab = conn.execute(
        "SELECT COUNT(*) FROM lead_master WHERE COALESCE(lab_context_score,0) >= 0.8"
    ).fetchone()[0]
    matched = 0
    try:
        matched = conn.execute("SELECT COUNT(DISTINCT lead_id) FROM lead_matches_existing_orgs").fetchone()[0]
    except sqlite3.OperationalError:
        matched = 0

    _print_kv("total_leads", total)
    _print_kv("with_equipment_tags", with_eq)
    _print_kv("with_lab_context>=0.8", with_lab)
    _print_kv("matched_to_org_master", matched)
    print("")
    print("counts_by_source:")
    for s, c in by_source:
        print(f"  - {s}: {c}")
    print("")
    print("counts_by_fit_bucket:")
    for fb, c in by_fit:
        print(f"  - {fb}: {c}")

    print("")
    print(f"top_{args.top}_by_score:")
    rows = conn.execute(
        """
        SELECT source_name, org_name, region, lead_type, equipment_match_tags, lab_context_score, fit_bucket,
               priority_score, priority_reason, evidence_summary, source_url
        FROM lead_master
        ORDER BY COALESCE(priority_score,0) DESC, last_seen_at DESC
        LIMIT ?
        """,
        (args.top,),
    ).fetchall()
    for r in rows:
        print("---")
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | fit={r[6]} | score={r[7]}")
        print(f"equip={r[4]} lab_ctx={r[5]}")
        print(f"reason={r[8]}")
        print(f"evidence={str(r[9] or '')[:220]}")
        print(f"url={r[10]}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

