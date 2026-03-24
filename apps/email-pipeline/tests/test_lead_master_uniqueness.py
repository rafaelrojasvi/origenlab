"""lead_master (source_name, source_record_id) uniqueness, upsert, and dedupe."""

from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.lead_master_dedupe import apply_lead_master_dedupe
from origenlab_email_pipeline.lead_master_keys import (
    backfill_canonical_source_record_ids,
    canonical_source_record_id,
    list_duplicate_key_groups,
)
from origenlab_email_pipeline.lead_normalize_upsert import upsert_lead_master_row
from origenlab_email_pipeline.leads_schema import (
    finalize_lead_master_source_keys,
    ensure_leads_tables_ddl_base,
)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def test_canonical_source_record_id() -> None:
    assert canonical_source_record_id(None) == ""
    assert canonical_source_record_id("  ") == ""
    assert canonical_source_record_id("  x  ") == "x"


def test_finalize_unique_index_on_fresh_db() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='uidx_lead_master_source_name_record'"
    ).fetchone()
    assert row is not None


def test_finalize_raises_when_duplicate_keys() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('src', 'k1', 'A', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('src', 'k1', 'B', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    with pytest.raises(RuntimeError, match="duplicate"):
        finalize_lead_master_source_keys(conn)


def test_upsert_on_conflict_preserves_first_seen_and_priority_columns() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    now1 = "2025-01-01T00:00:00Z"
    now2 = "2025-06-01T00:00:00Z"
    row1 = {
        "source_name": "chilecompra",
        "source_type": "procurement",
        "source_record_id": "T1",
        "source_url": "https://example.com/1",
        "org_name": "Org One",
        "contact_name": None,
        "email": None,
        "phone": None,
        "website": None,
        "domain": None,
        "region": None,
        "city": None,
        "lead_type": "tender_buyer",
        "organization_type_guess": "business",
        "equipment_match_tags": None,
        "buyer_kind": None,
        "lab_context_score": None,
        "lab_context_tags": None,
        "evidence_summary": "e1",
        "first_seen_at": now1,
        "last_seen_at": now1,
        "status": "nuevo",
        "email_norm": "",
        "domain_norm": "",
        "org_name_norm": "",
    }
    upsert_lead_master_row(conn, dict(row1))
    conn.execute(
        "UPDATE lead_master SET priority_score = 9.5, fit_bucket = 'high_fit' WHERE source_name = 'chilecompra'"
    )
    conn.commit()
    row2 = dict(row1)
    row2["org_name"] = "Org One Updated"
    row2["evidence_summary"] = "e2"
    row2["first_seen_at"] = now2
    row2["last_seen_at"] = now2
    row2["email"] = "buyer@example.org"
    upsert_lead_master_row(conn, row2)
    conn.commit()
    r = conn.execute(
        """
        SELECT org_name, evidence_summary, first_seen_at, last_seen_at,
               priority_score, fit_bucket, email
        FROM lead_master WHERE source_name = 'chilecompra' AND source_record_id = 'T1'
        """
    ).fetchone()
    assert r is not None
    assert r[0] == "Org One Updated"
    assert r[1] == "e2"
    assert r[2] == now1
    assert r[3] == now2
    assert r[4] == 9.5
    assert r[5] == "high_fit"
    assert r[6] == "buyer@example.org"


def test_upsert_empty_incoming_contact_preserves_existing() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    now = "2025-01-01T00:00:00Z"
    base = {
        "source_name": "chilecompra",
        "source_type": "procurement",
        "source_record_id": "T2",
        "source_url": None,
        "org_name": "O",
        "contact_name": "Pat",
        "email": "pat@x.cl",
        "phone": "1",
        "website": None,
        "domain": None,
        "region": None,
        "city": None,
        "lead_type": "tender_buyer",
        "organization_type_guess": "business",
        "equipment_match_tags": None,
        "buyer_kind": None,
        "lab_context_score": None,
        "lab_context_tags": None,
        "evidence_summary": "e",
        "first_seen_at": now,
        "last_seen_at": now,
        "status": "nuevo",
        "email_norm": "",
        "domain_norm": "",
        "org_name_norm": "",
    }
    upsert_lead_master_row(conn, dict(base))
    conn.commit()
    bump = dict(base)
    bump["contact_name"] = ""
    bump["email"] = None
    bump["phone"] = "   "
    bump["last_seen_at"] = "2025-02-01T00:00:00Z"
    upsert_lead_master_row(conn, bump)
    conn.commit()
    cn, em, ph = conn.execute(
        "SELECT contact_name, email, phone FROM lead_master WHERE source_record_id = 'T2'"
    ).fetchone()
    assert cn == "Pat"
    assert em == "pat@x.cl"
    assert ph == "1"


def test_apply_dedupe_merges_two_rows() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'dup', 'A', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'dup', 'B', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    assert len(list_duplicate_key_groups(conn)) == 1
    stats = apply_lead_master_dedupe(conn)
    assert stats.groups_merged == 1
    assert stats.leads_deleted == 1
    assert conn.execute("SELECT COUNT(*) FROM lead_master WHERE source_name='s'").fetchone()[0] == 1
    idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='uidx_lead_master_source_name_record'"
    ).fetchone()
    assert idx is not None


def test_whitespace_source_record_id_collapses_then_dedupe() -> None:
    """Canonical backfill makes '  x  ' and 'x' the same key; dedupe merges before unique index."""
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', '  x  ', 'A', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'x', 'B', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    backfill_canonical_source_record_ids(conn)
    assert len(list_duplicate_key_groups(conn)) == 1
    apply_lead_master_dedupe(conn)
    assert conn.execute("SELECT COUNT(*) FROM lead_master WHERE source_name='s'").fetchone()[0] == 1
