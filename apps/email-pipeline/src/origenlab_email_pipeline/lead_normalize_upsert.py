"""Upsert lead_master from normalized rows (conflict-safe vs UNIQUE source key)."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.lead_identity_norm import compute_lead_norm_fields
from origenlab_email_pipeline.lead_master_keys import canonical_source_record_id

LEAD_MASTER_COLS = [
    "source_name",
    "source_type",
    "source_record_id",
    "source_url",
    "org_name",
    "contact_name",
    "email",
    "phone",
    "website",
    "domain",
    "region",
    "city",
    "lead_type",
    "organization_type_guess",
    "equipment_match_tags",
    "buyer_kind",
    "lab_context_score",
    "lab_context_tags",
    "evidence_summary",
    "first_seen_at",
    "last_seen_at",
    "status",
    "email_norm",
    "domain_norm",
    "org_name_norm",
    "upstream_sync_state",
    "upstream_retired_at",
    "upstream_retired_reason",
]

_ON_CONFLICT_SET = """
  source_type = excluded.source_type,
  source_url = excluded.source_url,
  org_name = excluded.org_name,
  contact_name = COALESCE(NULLIF(TRIM(excluded.contact_name), ''), lead_master.contact_name),
  email = COALESCE(NULLIF(TRIM(excluded.email), ''), lead_master.email),
  phone = COALESCE(NULLIF(TRIM(excluded.phone), ''), lead_master.phone),
  website = excluded.website,
  domain = excluded.domain,
  region = excluded.region,
  city = excluded.city,
  lead_type = excluded.lead_type,
  organization_type_guess = excluded.organization_type_guess,
  equipment_match_tags = excluded.equipment_match_tags,
  buyer_kind = excluded.buyer_kind,
  lab_context_score = excluded.lab_context_score,
  lab_context_tags = excluded.lab_context_tags,
  evidence_summary = excluded.evidence_summary,
  first_seen_at = lead_master.first_seen_at,
  last_seen_at = excluded.last_seen_at,
  email_norm = excluded.email_norm,
  domain_norm = excluded.domain_norm,
  org_name_norm = excluded.org_name_norm,
  upstream_sync_state = 'active',
  upstream_retired_at = NULL,
  upstream_retired_reason = NULL
""".strip()


def upsert_lead_master_row(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or update lead_master on (source_name, source_record_id).

    Preserves first_seen_at and merges contact fields like pick_contact_field_for_upsert.
    """
    norms = compute_lead_norm_fields(row.get("email"), row.get("domain"), row.get("org_name"))
    row = {**row, **norms}
    row["source_record_id"] = canonical_source_record_id(row.get("source_record_id"))
    if row.get("upstream_sync_state") is None:
        row["upstream_sync_state"] = "active"
    cols = LEAD_MASTER_COLS
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"""
        INSERT INTO lead_master ({", ".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(source_name, source_record_id) DO UPDATE SET
        {_ON_CONFLICT_SET}
    """
    conn.execute(sql, tuple(row.get(c) for c in cols))
