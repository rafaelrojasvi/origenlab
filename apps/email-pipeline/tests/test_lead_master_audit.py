"""Read-only lead_master source-key audit (blank keys, per-source stats, formatting)."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

from origenlab_email_pipeline.lead_master_audit import (
    collect_lead_master_identity_audit,
    count_blank_canonical_leads,
    count_total_leads,
    format_audit_report_lines,
    sample_blank_rows,
    sample_duplicate_rows,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def test_empty_lead_master_audit_stable() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    db = Path("/tmp/audit_empty.sqlite")
    audit = collect_lead_master_identity_audit(conn, db)
    assert audit.total_leads == 0
    assert audit.total_blank_canonical == 0
    assert audit.global_duplicate_groups == 0
    assert audit.sources == []
    lines = format_audit_report_lines(audit, sample_limit=3, conn=conn)
    text = "\n".join(lines)
    assert "SUMMARY" in text
    assert "Total lead_master rows: 0" in text
    assert "PER-SOURCE IDENTITY" in text


def test_blank_canonical_counting_and_grouping_by_source() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at, source_url
        ) VALUES
          ('chilecompra', '  ', 'A', 'nuevo', ?, ?, 'http://a'),
          ('chilecompra', NULL, 'B', 'nuevo', ?, ?, NULL),
          ('inn_labs', 'x1', 'C', 'nuevo', ?, ?, NULL)
        """,
        (now, now, now, now, now, now),
    )
    conn.commit()
    assert count_total_leads(conn) == 3
    assert count_blank_canonical_leads(conn) == 2
    audit = collect_lead_master_identity_audit(conn, Path("mem.sqlite"))
    by = {s.source_name: s for s in audit.sources}
    assert by["chilecompra"].blank_canonical_count == 2
    assert by["chilecompra"].total_leads == 2
    assert by["inn_labs"].blank_canonical_count == 0
    assert by["inn_labs"].total_leads == 1
    assert by["chilecompra"].pct_blank == 100.0


def test_weak_id_and_duplicate_per_source() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('testsrc', 'k', 'O1', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('testsrc', 'k', 'O2', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    audit = collect_lead_master_identity_audit(conn, Path("mem.sqlite"))
    assert audit.global_duplicate_groups == 1
    row = next(s for s in audit.sources if s.source_name == "testsrc")
    assert row.duplicate_key_groups == 1
    assert row.duplicate_surplus_rows == 1
    hr, reasons = row.high_risk()
    assert hr
    assert "has_duplicate_key_groups" in reasons


def test_sample_blank_and_duplicate_rows() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', '', 'BlankOrg', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'd', 'D1', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('s', 'd', 'D2', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    blanks = sample_blank_rows(conn, source_name="s", limit=5)
    assert len(blanks) == 1
    assert blanks[0][3] == ""
    dups = sample_duplicate_rows(conn, source_name="s", limit=10)
    assert len(dups) == 2
    assert dups[0][3] == "d" and dups[1][3] == "d"


def test_chilecompra_short_numeric_heuristic_flags_high_risk() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    for rid in ("0", "1", "2"):
        conn.execute(
            """
            INSERT INTO lead_master (
              source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
            ) VALUES ('chilecompra', ?, 'Org', 'nuevo', ?, ?)
            """,
            (rid, now, now),
        )
    conn.commit()
    audit = collect_lead_master_identity_audit(conn, Path("mem.sqlite"))
    row = next(s for s in audit.sources if s.source_name == "chilecompra")
    assert row.suspect_short_numeric_ids == 3
    hr, reasons = row.high_risk()
    assert hr
    assert "chilecompra_many_short_numeric_ids_check_row_index_fallback" in reasons


def test_audit_script_exits_2_when_db_missing(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "leads" / "audit_lead_master_duplicates.py"
    spec = importlib.util.spec_from_file_location("audit_lead_master_duplicates", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    bogus = tmp_path / "no_such_dir" / "missing.sqlite"
    argv = [
        "audit_lead_master_duplicates.py",
        "--db",
        str(bogus),
    ]
    old = sys.argv
    try:
        sys.argv = argv
        spec.loader.exec_module(mod)
        rc = mod.main()
    finally:
        sys.argv = old
    assert rc == 2


def test_format_includes_warnings_and_chilecompra_note() -> None:
    conn = _conn()
    ensure_leads_tables_ddl_base(conn)
    now = "2025-01-01T00:00:00Z"
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, status, first_seen_at, last_seen_at
        ) VALUES ('z', '', 'Zorg', 'nuevo', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    audit = collect_lead_master_identity_audit(conn, Path("/x.sqlite"))
    lines = format_audit_report_lines(audit, sample_limit=2, conn=conn)
    text = "\n".join(lines)
    assert "WARNINGS" in text
    assert "has_blank_canonical_source_record_id" in text
    assert "CHILECOMPRA NOTE" in text
    assert "fetch_chilecompra.py" in text
