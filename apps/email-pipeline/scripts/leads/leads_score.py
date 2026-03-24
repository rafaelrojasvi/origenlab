#!/usr/bin/env python3
"""Compute priority_score and priority_reason for all lead_master rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_upstream_reconcile import sql_upstream_active_bare
from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.leads_score import compute_priority_score, fit_bucket


def main() -> int:
    ap = argparse.ArgumentParser(description="Score leads: set priority_score and priority_reason")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)
    rows = conn.execute(
        f"""
        SELECT id, source_type, lead_type, equipment_match_tags, lab_context_score, buyer_kind, email, phone
        FROM lead_master
        WHERE {sql_upstream_active_bare()}
        """
    ).fetchall()
    for lead_id, source_type, lead_type, equipment_match_tags, lab_context_score, buyer_kind, email, phone in rows:
        score, reason = compute_priority_score(
            source_type, lead_type, equipment_match_tags, lab_context_score, buyer_kind, email, phone
        )
        fb = fit_bucket(
            priority_score=score,
            equipment_match_tags=equipment_match_tags,
            lab_context_score=lab_context_score,
            buyer_kind=buyer_kind,
        )
        conn.execute(
            "UPDATE lead_master SET priority_score = ?, priority_reason = ?, fit_bucket = ? WHERE id = ?",
            (score, reason, fb, lead_id),
        )
    conn.commit()
    conn.close()
    print(f"Updated priority_score and priority_reason for {len(rows)} leads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
