"""Tests for outbound preflight readiness (read-only assessment)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.outbound_core import resolve_outbound_sent_folders
from origenlab_email_pipeline.outbound_readiness_check import (
    assess_outbound_readiness,
    object_exists,
    table_exists,
)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def _minimal_outbound_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            folder TEXT,
            recipients TEXT,
            date_iso TEXT,
            date_raw TEXT
        );
        CREATE TABLE contact_email_suppression (email TEXT);
        CREATE TABLE outreach_contact_state (
            contact_email_norm TEXT,
            state TEXT
        );
        CREATE TABLE supplier_master (domain_norm TEXT);
        CREATE TABLE contact_master (
            email TEXT PRIMARY KEY,
            last_seen_at TEXT
        );
        CREATE TABLE organization_master (
            domain TEXT PRIMARY KEY,
            last_seen_at TEXT
        );
        CREATE TABLE opportunity_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_type TEXT NOT NULL,
            entity_kind TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            created_at TEXT
        );
        """
    )


def _seed_fresh_sent_and_mart(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc)
    d_sent = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d_mart = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d_sig = (now - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO emails (source_file, folder, recipients, date_iso)
        VALUES ('gmail:contacto@origenlab.cl/x', '[Gmail]/Enviados', 'buyer@cliente.cl', ?)
        """,
        (d_sent,),
    )
    conn.execute(
        "INSERT INTO contact_email_suppression (email) VALUES ('spam@x.cl')"
    )
    conn.execute(
        """
        INSERT INTO outreach_contact_state (contact_email_norm, state)
        VALUES ('old@y.cl', 'contacted')
        """
    )
    conn.execute("INSERT INTO supplier_master (domain_norm) VALUES ('proveedor.cl')")
    conn.execute(
        "INSERT INTO contact_master (email, last_seen_at) VALUES ('a@b.cl', ?)",
        (d_mart,),
    )
    conn.execute(
        "INSERT INTO organization_master (domain, last_seen_at) VALUES ('b.cl', ?)",
        (d_mart,),
    )
    conn.execute(
        """
        INSERT INTO opportunity_signals (signal_type, entity_kind, entity_key, created_at)
        VALUES ('t', 'contact', 'a@b.cl', ?)
        """,
        (d_sig,),
    )
    conn.commit()


def test_all_good_ready(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        _seed_fresh_sent_and_mart(conn)
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=False,
        )
    finally:
        ro.close()

    assert r.verdict == "ready"
    assert not r.warnings
    assert not r.errors
    assert r.sent["sent_email_rows"] == 1
    assert r.sent.get("canonical_contacto_gmail_rows") == 1
    assert r.sent["sent_recipient_norm_count"] >= 1
    assert r.sent["sent_folders"] == list(resolve_outbound_sent_folders(None))
    assert r.sidecars["suppression_rows"] == 1
    assert r.sidecars["outreach_blocking_rows"] == 1


def test_missing_required_table_not_ready(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        conn.execute("DROP TABLE contact_email_suppression")
        conn.commit()
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=False,
        )
    finally:
        ro.close()

    assert r.verdict == "not_ready"
    assert any("contact_email_suppression" in e for e in r.errors)


def test_sent_only_outside_configured_folders_warns(tmp_path: Path) -> None:
    """Mail exists for the Gmail account but not under the configured Sent folder labels."""
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        conn.execute(
            """
            INSERT INTO emails (source_file, folder, recipients, date_iso)
            VALUES ('gmail:contacto@origenlab.cl/x', '[Gmail]/Drafts', 'a@b.cl',
                    '2026-04-14T15:00:00+00:00')
            """
        )
        conn.execute("INSERT INTO contact_email_suppression (email) VALUES ('spam@x.cl')")
        conn.execute(
            """
            INSERT INTO outreach_contact_state (contact_email_norm, state)
            VALUES ('old@y.cl', 'contacted')
            """
        )
        conn.execute("INSERT INTO supplier_master (domain_norm) VALUES ('proveedor.cl')")
        conn.execute(
            "INSERT INTO contact_master (email, last_seen_at) VALUES ('a@b.cl', '2026-04-13T10:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO organization_master (domain, last_seen_at) VALUES ('b.cl', '2026-04-13T10:00:00+00:00')"
        )
        conn.execute(
            """
            INSERT INTO opportunity_signals (signal_type, entity_kind, entity_key, created_at)
            VALUES ('t', 'contact', 'a@b.cl', '2026-04-12T10:00:00+00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=False,
        )
    finally:
        ro.close()

    assert r.verdict == "ready_with_warnings"
    assert any(
        "No rows in `emails` for configured Gmail user + Sent folders" in w for w in r.warnings
    )


def test_empty_sent_warns(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        conn.execute(
            "INSERT INTO contact_email_suppression (email) VALUES ('x@y.cl')"
        )
        conn.commit()
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=False,
        )
    finally:
        ro.close()

    assert r.verdict == "ready_with_warnings"
    assert any("No rows in `emails`" in w for w in r.warnings)


def test_stale_sent_warns(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        conn.execute(
            """
            INSERT INTO emails (source_file, folder, recipients, date_iso)
            VALUES ('gmail:contacto@origenlab.cl/x', '[Gmail]/Enviados', 'a@b.cl',
                    '2020-01-01T00:00:00+00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=False,
        )
    finally:
        ro.close()

    assert r.verdict == "ready_with_warnings"
    assert any("Newest Sent message" in w for w in r.warnings)


def test_strict_commercial_missing_table_not_ready(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        conn.commit()
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=True,
        )
    finally:
        ro.close()

    assert r.verdict == "not_ready"
    assert any("opportunity_candidate" in e for e in r.errors)


def test_strict_commercial_empty_candidates_warning(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        conn.execute("CREATE TABLE opportunity_candidate (id INTEGER)")
        conn.execute(
            "CREATE VIEW v_commercial_candidate_queue AS SELECT id FROM opportunity_candidate"
        )
        conn.commit()
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=True,
        )
    finally:
        ro.close()

    assert r.verdict == "ready_with_warnings"
    assert any("zero rows" in w for w in r.warnings)


def test_json_summary_shape(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        _seed_fresh_sent_and_mart(conn)
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        r = assess_outbound_readiness(
            ro,
            sqlite_path=db,
            sqlite_exists=True,
            gmail_user="contacto@origenlab.cl",
            sent_folders=DEFAULT_SENT_FOLDERS,
            max_staleness_days=30.0,
            strict_commercial_required=False,
        )
    finally:
        ro.close()

    d = r.to_json_obj()
    json.dumps(d)  # serializable
    assert d["verdict"] == "ready"
    assert set(d["required_tables"].keys()) == {
        "emails",
        "contact_email_suppression",
        "outreach_contact_state",
        "supplier_master",
        "contact_master",
        "organization_master",
        "opportunity_signals",
    }
    assert "sent" in d and "mart" in d and "commercial" in d


def test_sqlite_file_missing() -> None:
    p = Path("/nonexistent/path/outbound.sqlite")
    r = assess_outbound_readiness(
        _connect(),
        sqlite_path=p,
        sqlite_exists=False,
        gmail_user="contacto@origenlab.cl",
        sent_folders=DEFAULT_SENT_FOLDERS,
        max_staleness_days=14.0,
        strict_commercial_required=False,
    )
    assert r.verdict == "not_ready"
    assert not r.sqlite_exists


def test_object_exists_view() -> None:
    conn = _connect()
    conn.execute("CREATE TABLE t (x INT)")
    conn.execute("CREATE VIEW v AS SELECT x FROM t")
    assert table_exists(conn, "v") is False
    assert object_exists(conn, "v") is True


def test_cli_writes_json_and_exits_zero_when_ready(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    try:
        _minimal_outbound_schema(conn)
        _seed_fresh_sent_and_mart(conn)
    finally:
        conn.close()

    out_json = tmp_path / "report.json"
    script = REPO / "scripts" / "qa" / "check_outbound_readiness.py"
    r = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "--gmail-user",
            "contacto@origenlab.cl",
            "--max-staleness-days",
            "30",
            "--json-out",
            str(out_json),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert out_json.is_file()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["verdict"] == "ready"
    assert "Verdict: ready" in r.stdout
