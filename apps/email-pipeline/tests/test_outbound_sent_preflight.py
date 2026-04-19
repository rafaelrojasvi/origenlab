"""Unit and CLI tests for Gmail Sent-history preflight (lead export)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from origenlab_email_pipeline.outbound_sent_preflight import (
    SentHistoryProbeResult,
    evaluate_sent_history_preflight,
    probe_sent_history,
    sent_preflight_summary_dict,
)

REPO = Path(__file__).resolve().parents[1]


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def test_probe_empty_sent_history_no_rows() -> None:
    conn = _conn()
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT NOT NULL, folder TEXT)"
    )
    conn.commit()
    p = probe_sent_history(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    conn.close()
    assert p.sent_row_count == 0
    assert p.parsed_recipient_count == 0
    assert p.distinct_folders_sample == ()


def test_probe_wrong_folder_exposes_distinct_sample() -> None:
    conn = _conn()
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT NOT NULL, folder TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (?, ?, ?)",
        ("x@y.cl", "gmail:contacto@origenlab.cl/inbox", "[Gmail]/Sent Mail"),
    )
    conn.commit()
    p = probe_sent_history(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    conn.close()
    assert p.sent_row_count == 0
    assert "[Gmail]/Sent Mail" in p.distinct_folders_sample


def test_probe_sent_rows_unparseable_recipients_fails_preflight() -> None:
    conn = _conn()
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT NOT NULL, folder TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (?, ?, ?)",
        ("", "gmail:contacto@origenlab.cl/s1", "[Gmail]/Enviados"),
    )
    conn.commit()
    p = probe_sent_history(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    conn.close()
    assert p.sent_row_count == 1
    assert p.parsed_recipient_count == 0
    o = evaluate_sent_history_preflight(p, allow_empty=False)
    assert o.ok is False
    assert o.errors


def test_probe_healthy_sent_passes() -> None:
    conn = _conn()
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT NOT NULL, folder TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (?, ?, ?)",
        ("To: ok@cliente.cl", "gmail:contacto@origenlab.cl/s1", "[Gmail]/Enviados"),
    )
    conn.commit()
    p = probe_sent_history(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    conn.close()
    assert p.sent_row_count == 1
    assert p.parsed_recipient_count == 1
    o = evaluate_sent_history_preflight(p, allow_empty=False)
    assert o.ok is True
    assert not o.errors


def test_allow_empty_override_ok_with_warnings() -> None:
    conn = _conn()
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT NOT NULL, folder TEXT)"
    )
    conn.commit()
    p = probe_sent_history(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    conn.close()
    o = evaluate_sent_history_preflight(p, allow_empty=True)
    assert o.ok is True
    assert o.override_used is True
    assert o.warnings
    d = sent_preflight_summary_dict(o)
    assert d["ok"] is True
    assert d["override_used"] is True


def test_evaluate_empty_gmail_user_errors_even_with_allow_empty() -> None:
    probe = SentHistoryProbeResult(
        gmail_user="",
        sent_folders=("[Gmail]/Enviados",),
        sent_row_count=0,
        parsed_recipient_count=0,
        distinct_folders_sample=(),
    )
    o = evaluate_sent_history_preflight(probe, allow_empty=True)
    assert o.ok is False
    assert o.errors


def _db_lead_only_no_sent(path: Path) -> None:
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables

    conn = sqlite3.connect(str(path))
    ensure_leads_tables(conn)
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, email, email_norm, fit_bucket, priority_score, status
        ) VALUES ('test', 'r1', 'Org A', 'buyer@external.cl', 'buyer@external.cl', 'high_fit', 8.0, 'nuevo')
        """
    )
    conn.commit()
    conn.close()


def test_export_next_marketing_cli_fails_preflight_without_sent_rows(tmp_path: Path) -> None:
    db = tmp_path / "leads.sqlite"
    _db_lead_only_no_sent(db)
    out_csv = tmp_path / "next.csv"
    script = REPO / "scripts" / "leads" / "export_next_marketing_recipients.py"
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "-o",
            str(out_csv),
            "--limit",
            "1",
            "--fetch-cap",
            "50",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 3, run.stdout + run.stderr
    assert "preflight failed" in run.stderr.lower() or "Sent-history" in run.stderr
    assert not out_csv.is_file()


def test_export_next_marketing_cli_allow_empty_writes_sent_preflight_in_summary(tmp_path: Path) -> None:
    db = tmp_path / "leads.sqlite"
    _db_lead_only_no_sent(db)
    out_csv = tmp_path / "next.csv"
    script = REPO / "scripts" / "leads" / "export_next_marketing_recipients.py"
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "-o",
            str(out_csv),
            "--limit",
            "1",
            "--fetch-cap",
            "50",
            "--allow-empty-sent-history",
            "--write-outbound-summary",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    assert "warning:" in run.stderr.lower()
    summary_path = tmp_path / "next_outbound_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    sp = payload["sent_preflight"]
    assert sp["ok"] is True
    assert sp["override_used"] is True
    assert sp["sent_row_count"] == 0
    assert sp["parsed_recipient_count"] == 0
    assert "contacto@origenlab.cl" in sp["gmail_user"]


def test_build_archive_send_batch_cli_fails_preflight_without_sent_rows(tmp_path: Path) -> None:
    """Archive lane matches lead export: exit 3 when Sent history is missing."""
    import importlib.util

    mod_path = REPO / "tests" / "test_build_archive_send_batch.py"
    spec = importlib.util.spec_from_file_location("test_build_archive_send_batch", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    db = tmp_path / "arch_no_sent.sqlite"
    mod._seed_db(db, with_sent_preflight=False)
    out_dir = tmp_path / "out_arch_preflight"
    script = REPO / "scripts" / "leads" / "build_archive_send_batch.py"
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "--out-dir",
            str(out_dir),
            "--shortlist-limit",
            "5",
            "--audit-limit",
            "20",
            "--allow-weak-warmth",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 3, run.stdout + run.stderr
    assert "preflight failed" in run.stderr.lower() or "sent-history" in run.stderr.lower()
    assert not (out_dir / "archive_outreach_build_summary.json").is_file()
