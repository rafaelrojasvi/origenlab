"""Smoke tests for sqlite_migrate orchestration and legacy-shaped DB upgrades."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.bi_views import refresh_lead_match_summary_view
from origenlab_email_pipeline.lead_accounts_schema import ensure_lead_account_tables
from origenlab_email_pipeline.leads_schema import ensure_leads_tables, ensure_leads_tables_ddl
from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def test_migrate_fresh_db_full_layers() -> None:
    conn = _connect()
    migrate_sqlite_schema(conn)
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='emails'"
    ).fetchone()
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_master'"
    ).fetchone()
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_master'"
    ).fetchone()
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_master'"
    ).fetchone()
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_lead_match_summary'"
    ).fetchone()
    st = refresh_lead_match_summary_view(conn)
    assert st == "ok"


def test_legacy_lead_master_without_norm_columns_migrates() -> None:
    conn = _connect()
    ensure_pipeline_meta_tables(conn)
    conn.executescript(
        """
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_name TEXT NOT NULL,
          source_type TEXT,
          source_record_id TEXT,
          source_url TEXT,
          org_name TEXT,
          contact_name TEXT,
          email TEXT,
          phone TEXT,
          website TEXT,
          domain TEXT,
          region TEXT,
          city TEXT,
          lead_type TEXT,
          organization_type_guess TEXT,
          evidence_summary TEXT,
          first_seen_at TEXT,
          last_seen_at TEXT,
          priority_score REAL,
          priority_reason TEXT,
          status TEXT DEFAULT 'nuevo',
          review_owner TEXT,
          last_reviewed_at TEXT,
          next_action TEXT,
          notes TEXT
        );
        """
    )
    migrate_sqlite_schema(conn, layers={SchemaLayer.LEADS})
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(lead_master)").fetchall()
    }
    assert "email_norm" in cols
    assert "domain_norm" in cols
    assert "org_name_norm" in cols
    assert "upstream_sync_state" in cols
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_upstream_reconcile_log'"
    ).fetchone()
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_lead_match_summary'"
    ).fetchone()
    assert refresh_lead_match_summary_view(conn) == "ok"


def test_legacy_lead_account_matches_without_pipeline_run_id() -> None:
    conn = _connect()
    ensure_pipeline_meta_tables(conn)
    ensure_leads_tables_ddl(conn)
    conn.executescript(
        """
        CREATE TABLE lead_account_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          account_dedupe_key TEXT NOT NULL UNIQUE,
          canonical_name TEXT NOT NULL,
          normalized_name TEXT NOT NULL,
          primary_domain TEXT,
          official_website TEXT,
          org_type TEXT,
          region TEXT,
          city TEXT,
          country TEXT NOT NULL DEFAULT 'CL',
          source_count INTEGER NOT NULL DEFAULT 0,
          lead_count INTEGER NOT NULL DEFAULT 0,
          first_seen_at TEXT,
          last_seen_at TEXT,
          quality_status TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE lead_account_matches_existing_orgs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          lead_account_id INTEGER NOT NULL,
          organization_domain TEXT NOT NULL,
          match_method TEXT NOT NULL,
          confidence REAL NOT NULL,
          evidence_json TEXT,
          review_status TEXT NOT NULL DEFAULT 'auto',
          created_at TEXT NOT NULL,
          UNIQUE(lead_account_id, organization_domain),
          FOREIGN KEY(lead_account_id) REFERENCES lead_account_master(id) ON DELETE CASCADE
        );
        """
    )
    ensure_lead_account_tables(conn, refresh_view=False)
    cols = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(lead_account_matches_existing_orgs)"
        ).fetchall()
    }
    assert "pipeline_run_id" in cols
    st = refresh_lead_match_summary_view(conn)
    assert st == "ok"


def test_migrate_sqlite_schema_legacy_combined() -> None:
    conn = _connect()
    ensure_pipeline_meta_tables(conn)
    conn.executescript(
        """
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_name TEXT NOT NULL,
          source_record_id TEXT,
          org_name TEXT,
          contact_name TEXT,
          email TEXT,
          domain TEXT,
          status TEXT DEFAULT 'nuevo',
          priority_score REAL,
          last_seen_at TEXT
        );
        """
    )
    migrate_sqlite_schema(
        conn,
        layers={SchemaLayer.LEADS, SchemaLayer.LEAD_ACCOUNTS},
        leads_backfill_norms=True,
    )
    assert "email_norm" in {
        row[1] for row in conn.execute("PRAGMA table_info(lead_master)").fetchall()
    }
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_account_master'"
    ).fetchone()
    assert refresh_lead_match_summary_view(conn) == "ok"


def test_ensure_leads_tables_ddl_separate_from_backfill_and_view() -> None:
    conn = _connect()
    ensure_pipeline_meta_tables(conn)
    conn.execute(
        """
        CREATE TABLE lead_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_name TEXT NOT NULL,
          source_record_id TEXT,
          email TEXT,
          domain TEXT,
          org_name TEXT,
          status TEXT DEFAULT 'nuevo',
          priority_score REAL,
          last_seen_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO lead_master (source_name, source_record_id, email) VALUES ('s', 'r', 'a@b.co')"
    )
    lid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    ensure_leads_tables_ddl(conn)
    row = conn.execute(
        "SELECT email_norm, domain_norm, org_name_norm FROM lead_master WHERE id = ?",
        (lid,),
    ).fetchone()
    assert row == (None, None, None)
    ensure_leads_tables(conn, backfill_norms=True, refresh_view=True)
    row2 = conn.execute(
        "SELECT email_norm, domain_norm, org_name_norm FROM lead_master WHERE id = ?",
        (lid,),
    ).fetchone()
    assert row2 is not None
