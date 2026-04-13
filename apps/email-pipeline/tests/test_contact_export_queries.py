"""Lock ``contact_master`` marketing / audit SQL shape and ordering."""

from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.contact_export_queries import (
    CONTACT_MASTER_CANDIDATE_AUDIT_COLUMN_NAMES,
    CONTACT_MASTER_MARKETING_EXPORT_COLUMN_NAMES,
    sql_contact_master_candidate_audit_contacts,
    sql_contact_master_marketing_export_candidates,
)

_CONTACT_MASTER_DDL = """
CREATE TABLE contact_master (
  email TEXT,
  contact_name_best TEXT,
  organization_name_guess TEXT,
  total_emails INTEGER,
  last_seen_at TEXT,
  confidence_score REAL
);
"""


def _conn_with_sample_rows() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_CONTACT_MASTER_DDL)
    conn.execute(
        "INSERT INTO contact_master (email, contact_name_best, organization_name_guess, "
        "total_emails, last_seen_at, confidence_score) VALUES (?, ?, ?, ?, ?, ?)",
        ("low@example.cl", "Low User", "Org Low", 1, "2020-06-01", 0.1),
    )
    conn.execute(
        "INSERT INTO contact_master (email, contact_name_best, organization_name_guess, "
        "total_emails, last_seen_at, confidence_score) VALUES (?, ?, ?, ?, ?, ?)",
        ("HIGH@Example.CL", "High User", "Org High", 99, "2019-01-01", 0.9),
    )
    conn.execute(
        "INSERT INTO contact_master (email, contact_name_best, organization_name_guess, "
        "total_emails, last_seen_at, confidence_score) VALUES (?, ?, ?, ?, ?, ?)",
        ("", "X", "Bad", 5, "2021-01-01", 0.5),
    )
    conn.execute(
        "INSERT INTO contact_master (email, contact_name_best, organization_name_guess, "
        "total_emails, last_seen_at, confidence_score) VALUES (?, ?, ?, ?, ?, ?)",
        ("no-at-sign", "Y", "Bad2", 5, "2021-01-02", 0.5),
    )
    return conn


def test_marketing_export_sql_column_names_and_ordering() -> None:
    conn = _conn_with_sample_rows()
    sql = sql_contact_master_marketing_export_candidates()
    cur = conn.execute(sql, (10,))
    assert tuple(d[0] for d in cur.description) == CONTACT_MASTER_MARKETING_EXPORT_COLUMN_NAMES
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "high@example.cl"
    assert rows[0][1] == "High User"
    assert rows[0][2] == "Org High"
    assert rows[0][3] == 99
    assert rows[0][4] == "2019-01-01"
    assert rows[0][5] == pytest.approx(0.9)
    assert rows[1][0] == "low@example.cl"
    conn.close()


def test_candidate_audit_sql_column_names_and_ordering() -> None:
    conn = _conn_with_sample_rows()
    sql = sql_contact_master_candidate_audit_contacts()
    cur = conn.execute(sql, (10,))
    assert tuple(d[0] for d in cur.description) == CONTACT_MASTER_CANDIDATE_AUDIT_COLUMN_NAMES
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "high@example.cl"
    assert rows[0][1] == "Org High"
    assert rows[0][2] == ""
    assert rows[0][3] is None
    conn.close()


def _norm_sql(s: str) -> str:
    return " ".join(s.split())


def test_export_and_audit_share_ranking_predicate() -> None:
    """Same FROM/WHERE/ORDER/LIMIT tail prevents silent drift between scripts."""
    export_sql = sql_contact_master_marketing_export_candidates()
    audit_sql = sql_contact_master_candidate_audit_contacts()
    tail = _norm_sql(
        """
FROM contact_master
WHERE email IS NOT NULL
  AND trim(email) != ''
  AND instr(email, '@') > 0
ORDER BY COALESCE(total_emails, 0) DESC, COALESCE(last_seen_at, '') DESC
LIMIT ?
"""
    )
    assert tail in _norm_sql(export_sql)
    assert tail in _norm_sql(audit_sql)


def test_limit_bound_respected() -> None:
    conn = _conn_with_sample_rows()
    cur = conn.execute(sql_contact_master_marketing_export_candidates(), (1,))
    assert len(cur.fetchall()) == 1
    conn.close()
