"""Upstream raw vs lead_master reconciliation (soft retire + normalize reactivate)."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.lead_normalize_upsert import upsert_lead_master_row
from origenlab_email_pipeline.lead_upstream_reconcile import (
    RETIRED_UPSTREAM_STATE,
    list_retire_candidates,
    run_upstream_reconcile,
    sources_with_raw_snapshot,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base, finalize_lead_master_source_keys


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _minimal_leads(conn: sqlite3.Connection) -> None:
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)


def test_sources_with_raw_snapshot() -> None:
    conn = _conn()
    _minimal_leads(conn)
    conn.execute(
        """
        INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json)
        VALUES ('s1', 'a', 't', '{}')
        """
    )
    conn.commit()
    assert sources_with_raw_snapshot(conn) == {"s1"}


def test_no_retire_when_raw_empty_for_source() -> None:
    """Conservative: zero raw rows for a source → do not retire that source's masters."""
    conn = _conn()
    _minimal_leads(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('orphan_src', 'k1', 'O', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    finalize_lead_master_source_keys(conn)
    cands, warns = list_retire_candidates(conn, only_sources=None)
    assert cands == []
    assert not warns


def test_retire_candidate_when_key_missing_from_raw() -> None:
    conn = _conn()
    _minimal_leads(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json)
        VALUES ('src', 'keep', 't', '{}')
        """,
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('src', 'gone', 'G', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    finalize_lead_master_source_keys(conn)
    cands, _ = list_retire_candidates(conn)
    assert len(cands) == 1
    lid, sn, sk = cands[0]
    assert sn == "src" and sk == "gone"
    row = conn.execute("SELECT id FROM lead_master WHERE source_name='src' AND source_record_id='gone'").fetchone()
    assert row and int(row[0]) == lid


def test_dry_run_does_not_write() -> None:
    conn = _conn()
    _minimal_leads(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json) VALUES ('s','k','t','{}')",
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'x', 'X', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    finalize_lead_master_source_keys(conn)
    r = run_upstream_reconcile(conn, dry_run=True)
    assert len(r.retire_candidates) == 1
    st = conn.execute(
        "SELECT upstream_sync_state FROM lead_master WHERE source_record_id='x'"
    ).fetchone()[0]
    assert st in (None, "active")
    nlog = conn.execute("SELECT COUNT(*) FROM lead_upstream_reconcile_log").fetchone()[0]
    assert int(nlog) == 0


def test_apply_retires_and_logs() -> None:
    conn = _conn()
    _minimal_leads(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json) VALUES ('s','k','t','{}')",
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'x', 'X', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    finalize_lead_master_source_keys(conn)
    r = run_upstream_reconcile(conn, dry_run=False)
    assert r.retired_applied == 1
    st = conn.execute(
        "SELECT upstream_sync_state FROM lead_master WHERE source_record_id='x'"
    ).fetchone()[0]
    assert st == RETIRED_UPSTREAM_STATE
    nlog = conn.execute("SELECT COUNT(*) FROM lead_upstream_reconcile_log").fetchone()[0]
    assert int(nlog) == 1


def test_normalize_upsert_reactivates_retired() -> None:
    conn = _conn()
    _minimal_leads(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json) VALUES ('s','k','t','{}')",
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'x', 'X', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    finalize_lead_master_source_keys(conn)
    run_upstream_reconcile(conn, dry_run=False)
    # Raw row for 'x' appears again
    conn.execute(
        "INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json) VALUES ('s','x','t2','{}')",
    )
    conn.commit()
    upsert_lead_master_row(
        conn,
        {
            "source_name": "s",
            "source_type": None,
            "source_record_id": "x",
            "source_url": None,
            "org_name": "X2",
            "contact_name": None,
            "email": None,
            "phone": None,
            "website": None,
            "domain": None,
            "region": None,
            "city": None,
            "lead_type": None,
            "organization_type_guess": None,
            "equipment_match_tags": None,
            "buyer_kind": None,
            "lab_context_score": None,
            "lab_context_tags": None,
            "evidence_summary": None,
            "first_seen_at": now,
            "last_seen_at": now,
            "status": "nuevo",
        },
    )
    conn.commit()
    st = conn.execute(
        "SELECT upstream_sync_state FROM lead_master WHERE source_record_id='x'"
    ).fetchone()[0]
    assert st == "active"
    reason = conn.execute(
        "SELECT upstream_retired_reason FROM lead_master WHERE source_record_id='x'"
    ).fetchone()[0]
    assert reason is None
