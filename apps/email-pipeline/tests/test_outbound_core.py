"""Tests for shared outbound defaults (outbound_core)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.config import Settings
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.outbound_core import (
    OUTBOUND_RUN_SUMMARY_SCHEMA_VERSION,
    build_outbound_run_envelope,
    gate_context_for_archive_batch,
    gate_context_for_lead_master_export,
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
    sent_folder_defaults_were_used,
)

REPO = Path(__file__).resolve().parents[1]


def test_resolve_gmail_user_explicit_over_settings() -> None:
    s = MagicMock(spec=Settings)
    s.gmail_workspace_user = "from@settings.cl"
    assert resolve_outbound_gmail_user(s, explicit="cli@x.cl") == "cli@x.cl"


def test_resolve_gmail_user_falls_back_to_settings_then_constant() -> None:
    s = MagicMock(spec=Settings)
    s.gmail_workspace_user = "from@settings.cl"
    assert resolve_outbound_gmail_user(s, explicit=None) == "from@settings.cl"
    s.gmail_workspace_user = None
    assert resolve_outbound_gmail_user(s, explicit=None) == "contacto@origenlab.cl"


def test_resolve_sent_folders_defaults_match_marketing_export_context() -> None:
    assert resolve_outbound_sent_folders(None) == DEFAULT_SENT_FOLDERS
    assert resolve_outbound_sent_folders([]) == DEFAULT_SENT_FOLDERS


def test_sent_folder_defaults_were_used() -> None:
    assert sent_folder_defaults_were_used(None) is True
    assert sent_folder_defaults_were_used([]) is True
    assert sent_folder_defaults_were_used(["  "]) is True
    assert sent_folder_defaults_were_used(["[Gmail]/Enviados"]) is False


def test_gate_context_helpers_match_direct_build(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT, folder TEXT, date_iso TEXT, date_raw TEXT);"
    )
    conn.commit()
    from origenlab_email_pipeline.marketing_export_context import build_marketing_export_gate_context

    g_archive = gate_context_for_archive_batch(
        conn,
        gmail_user="u@x.cl",
        sent_folders=("[Gmail]/Enviados",),
        extra_exclude_domains=("x.cl",),
        strict_contact_graph_noise=True,
    )
    g_direct_a = build_marketing_export_gate_context(
        conn,
        gmail_user="u@x.cl",
        sent_folders=("[Gmail]/Enviados",),
        extra_exclude_domains=("x.cl",),
        strict_contact_graph_noise=True,
    )
    assert g_archive == g_direct_a

    g_lead = gate_context_for_lead_master_export(
        conn,
        gmail_user="u@x.cl",
        sent_folders=("[Gmail]/Enviados",),
        extra_exclude_domains=("x.cl",),
    )
    g_direct_l = build_marketing_export_gate_context(
        conn,
        gmail_user="u@x.cl",
        sent_folders=("[Gmail]/Enviados",),
        extra_exclude_domains=("x.cl",),
        strict_contact_graph_noise=False,
    )
    assert g_lead == g_direct_l
    conn.close()


def test_outbound_run_envelope_stable_keys() -> None:
    env = build_outbound_run_envelope(
        lane="lead",
        gmail_user="g@x.cl",
        sqlite_path="/tmp/x.sqlite",
        sent_folders=("[Gmail]/Enviados",),
        sent_folder_defaults_used=False,
        strict_contact_graph_noise=False,
        extra_exclude_domains=("a.cl",),
        created_at_utc="2026-04-15T00:00:00+00:00",
        artifact_paths={"marketing_csv": "/out/a.csv"},
        counts={"n_exported": 3},
    )
    assert env["schema_version"] == OUTBOUND_RUN_SUMMARY_SCHEMA_VERSION
    for k in (
        "lane",
        "gmail_user",
        "sqlite_path",
        "sent_folders_resolved",
        "sent_folder_defaults_used",
        "strict_contact_graph_noise",
        "extra_exclude_domains",
        "created_at_utc",
        "artifact_paths",
        "counts",
    ):
        assert k in env


def test_build_archive_cli_includes_outbound_run_in_summary(tmp_path: Path) -> None:
    """Regression: canonical archive CLI writes shared outbound_run envelope."""
    import importlib.util

    mod_path = REPO / "tests" / "test_build_archive_send_batch.py"
    spec = importlib.util.spec_from_file_location("test_build_archive_send_batch", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    db = tmp_path / "t.sqlite"
    mod._seed_db(db)
    out_dir = tmp_path / "out_cli"
    script = REPO / "scripts" / "leads" / "build_archive_send_batch.py"
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "--out-dir",
            str(out_dir),
            "--build-batch",
            "--shortlist-limit",
            "10",
            "--audit-limit",
            "100",
            "--allow-weak-warmth",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    summary_path = out_dir / "archive_outreach_build_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "outbound_run" in summary
    orun = summary["outbound_run"]
    assert orun["lane"] == "archive"
    assert orun["sent_folder_defaults_used"] is True
    assert orun["sent_folders_resolved"] == list(DEFAULT_SENT_FOLDERS)
    assert orun["strict_contact_graph_noise"] is True
    assert "sent_preflight" in summary
    sp = summary["sent_preflight"]
    assert sp["ok"] is True
    assert sp["override_used"] is False


def _minimal_db_for_lead_export(path: Path) -> None:
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables

    conn = sqlite3.connect(str(path))
    ensure_leads_tables(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            folder TEXT,
            recipients TEXT,
            date_iso TEXT,
            date_raw TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO emails (source_file, folder, recipients, date_iso)
        VALUES (
            'gmail:contacto@origenlab.cl/sent1',
            '[Gmail]/Enviados',
            'prior@cliente.cl',
            '2026-04-15T12:00:00+00:00'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO lead_master (
          source_name, source_record_id, org_name, email, email_norm, fit_bucket, priority_score, status
        ) VALUES ('test', 'r1', 'Org A', 'buyer@external.cl', 'buyer@external.cl', 'high_fit', 8.0, 'nuevo')
        """
    )
    conn.commit()
    conn.close()


def test_export_next_marketing_cli_writes_outbound_summary(tmp_path: Path) -> None:
    db = tmp_path / "leads.sqlite"
    _minimal_db_for_lead_export(db)
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
            "--write-outbound-summary",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    summary_path = tmp_path / "next_outbound_summary.json"
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["outbound_run"]["lane"] == "lead"
    assert payload["outbound_run"]["strict_contact_graph_noise"] is False
    assert payload["outbound_run"]["sent_folders_resolved"] == list(DEFAULT_SENT_FOLDERS)
    assert "lead_queue" in payload
    sp = payload["sent_preflight"]
    assert sp["ok"] is True
    assert sp["override_used"] is False
    assert sp["sent_row_count"] >= 1
    assert sp["parsed_recipient_count"] >= 1
    assert sp["gmail_user"] == "contacto@origenlab.cl"


