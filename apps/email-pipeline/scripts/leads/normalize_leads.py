#!/usr/bin/env python3
"""Normalize external_leads_raw into lead_master. Optionally ensure schema only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_identity_norm import compute_lead_norm_fields
from origenlab_email_pipeline.leads_normalize import pick_contact_field_for_upsert, raw_to_normalized
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

LEAD_MASTER_COLS = [
    "source_name", "source_type", "source_record_id", "source_url",
    "org_name", "contact_name", "email", "phone", "website", "domain",
    "region", "city", "lead_type", "organization_type_guess", "equipment_match_tags",
    "buyer_kind", "lab_context_score", "lab_context_tags",
    "evidence_summary", "first_seen_at", "last_seen_at", "status",
    "email_norm", "domain_norm", "org_name_norm",
]


def upsert_lead(conn, row: dict) -> None:
    """Update existing lead by (source_name, source_record_id) or insert."""
    norms = compute_lead_norm_fields(row.get("email"), row.get("domain"), row.get("org_name"))
    row = {**row, **norms}
    cur = conn.execute(
        "SELECT id FROM lead_master WHERE source_name = ? AND source_record_id = ?",
        (row["source_name"], row.get("source_record_id") or ""),
    )
    existing = cur.fetchone()
    if existing:
        lead_id = existing[0]
        prev = conn.execute(
            "SELECT contact_name, email, phone FROM lead_master WHERE id = ?",
            (lead_id,),
        ).fetchone()
        old_name, old_email, old_phone = (prev or (None, None, None))
        contact_name = pick_contact_field_for_upsert(row.get("contact_name"), old_name)
        email = pick_contact_field_for_upsert(row.get("email"), old_email)
        phone = pick_contact_field_for_upsert(row.get("phone"), old_phone)
        conn.execute(
            """
            UPDATE lead_master SET
              source_type = ?, source_url = ?, org_name = ?, contact_name = ?, email = ?, phone = ?, website = ?,
              domain = ?, region = ?, city = ?, lead_type = ?, organization_type_guess = ?, equipment_match_tags = ?,
              buyer_kind = ?, lab_context_score = ?, lab_context_tags = ?,
              evidence_summary = ?, last_seen_at = ?,
              email_norm = ?, domain_norm = ?, org_name_norm = ?
            WHERE id = ?
            """,
            (
                row.get("source_type"), row.get("source_url"), row.get("org_name"), contact_name,
                email, phone, row.get("website"), row.get("domain"),
                row.get("region"), row.get("city"), row.get("lead_type"), row.get("organization_type_guess"),
                row.get("equipment_match_tags"), row.get("buyer_kind"), row.get("lab_context_score"), row.get("lab_context_tags"),
                row.get("evidence_summary"), row.get("last_seen_at"),
                row.get("email_norm"), row.get("domain_norm"), row.get("org_name_norm"),
                lead_id,
            ),
        )
    else:
        placeholders = ", ".join(["?"] * len(LEAD_MASTER_COLS))
        conn.execute(
            f"INSERT INTO lead_master ({', '.join(LEAD_MASTER_COLS)}) VALUES ({placeholders})",
            tuple(row.get(c) for c in LEAD_MASTER_COLS),
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize raw leads into lead_master")
    ap.add_argument("--ensure-schema-only", action="store_true", help="Only create lead tables and exit")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    # Long-running upserts benefit from a busy timeout under WAL mode.
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_leads_tables(conn)
    if args.ensure_schema_only:
        conn.close()
        print("Lead tables ensured.")
        return 0
    rows = conn.execute("SELECT source_name, source_record_id, raw_json FROM external_leads_raw").fetchall()
    n = 0
    batch = 0
    for source_name, source_record_id, raw_json in rows:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or {})
        except (json.JSONDecodeError, TypeError):
            raw = {}
        if not isinstance(raw, dict):
            continue
        try:
            normalized = raw_to_normalized(source_name, raw)
        except Exception as e:
            print(f"Warning: skip raw {source_name}/{source_record_id}: {e}", file=sys.stderr)
            continue
        normalized["source_record_id"] = source_record_id
        upsert_lead(conn, normalized)
        n += 1
        batch += 1
        # Commit periodically so results are visible and to reduce long transactions.
        if batch >= 2000:
            conn.commit()
            batch = 0
            if n % 10000 == 0:
                print(f"…normalized {n}/{len(rows)}", file=sys.stderr)
    conn.commit()
    conn.close()
    print(f"Normalized {n} leads into lead_master.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
