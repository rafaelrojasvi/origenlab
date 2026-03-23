"""Tests for matching leads to organization_master (domain and name)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.business_mart_schema import BUSINESS_MART_SCHEMA_SQL
from origenlab_email_pipeline.leads_match import _normalize_name_for_match, match_leads_to_mart
from origenlab_email_pipeline.leads_schema import ensure_leads_tables


def test_normalize_name_for_match() -> None:
    assert _normalize_name_for_match("  Acme S.A.  ") == "acme"
    assert _normalize_name_for_match("Lab SpA") == "lab"
    assert _normalize_name_for_match("Universidad de Chile") == "universidad de chile"
    assert _normalize_name_for_match(None) == ""
    assert _normalize_name_for_match("") == ""


def test_match_leads_to_mart_domain() -> None:
    tmp = Path(__file__).resolve().parent / "tmp_leads_match.db"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    conn.executescript(BUSINESS_MART_SCHEMA_SQL)
    ensure_leads_tables(conn)
    conn.execute(
        "INSERT INTO organization_master (domain, organization_name_guess) VALUES (?, ?)",
        ("buyer.gob.cl", "Comprador Publico"),
    )
    conn.execute(
        """INSERT INTO lead_master (id, source_name, source_record_id, org_name, domain)
           VALUES (1, 'chilecompra', 'tid-1', 'Comprador Publico', 'buyer.gob.cl')"""
    )
    conn.commit()
    org_n, contact_n = match_leads_to_mart(conn)
    conn.close()
    assert org_n >= 1
    assert contact_n >= 0
    conn2 = sqlite3.connect(str(tmp))
    rows = conn2.execute("SELECT lead_id, matched_domain, match_type FROM lead_matches_existing_orgs").fetchall()
    conn2.close()
    assert any(r[1] == "buyer.gob.cl" and r[2] == "domain" for r in rows)
    tmp.unlink()


def test_match_no_mart_table() -> None:
    tmp = Path(__file__).resolve().parent / "tmp_leads_no_mart.db"
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    ensure_leads_tables(conn)
    conn.execute(
        """INSERT INTO lead_master (id, source_name, source_record_id, org_name, domain)
           VALUES (1, 'inn_labs', 'L1', 'Lab X', NULL)"""
    )
    conn.commit()
    # organization_master does not exist
    org_n, contact_n = match_leads_to_mart(conn)
    conn.close()
    assert (org_n, contact_n) == (0, 0)
    tmp.unlink()
