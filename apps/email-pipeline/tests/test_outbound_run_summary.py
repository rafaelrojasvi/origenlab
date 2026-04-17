"""Tests for outbound summary JSON trust report helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.outbound_run_summary import (
    extract_outbound_run,
    format_outbound_run_trust_report,
    load_summary_json,
    trust_report_from_summary_path,
)

REPO = Path(__file__).resolve().parents[1]


def test_extract_nested_outbound_run() -> None:
    summary = {
        "send_ready_rows": 3,
        "outbound_run": {
            "schema_version": "1",
            "lane": "archive",
            "gmail_user": "g@test.cl",
            "sqlite_path": "/tmp/x.sqlite",
            "sent_folders_resolved": ["[Gmail]/Enviados"],
            "sent_folder_defaults_used": True,
            "strict_contact_graph_noise": True,
            "extra_exclude_domains": [],
            "created_at_utc": "2026-04-15T00:00:00+00:00",
            "artifact_paths": {"send_ready_csv": "/out/send.csv"},
            "counts": {"send_ready_rows": 3, "gate_blocked_rows": 1},
        },
    }
    run = extract_outbound_run(summary)
    assert run["lane"] == "archive"
    assert run["counts"]["gate_blocked_rows"] == 1


def test_extract_root_envelope() -> None:
    summary = {
        "schema_version": "1",
        "lane": "lead",
        "gmail_user": "g@test.cl",
        "sqlite_path": "/db.sqlite",
        "sent_folders_resolved": [],
        "sent_folder_defaults_used": False,
        "strict_contact_graph_noise": False,
        "extra_exclude_domains": [],
        "created_at_utc": "t",
        "artifact_paths": {},
        "counts": {},
    }
    assert extract_outbound_run(summary) is summary


def test_extract_missing_raises() -> None:
    with pytest.raises(KeyError):
        extract_outbound_run({"send_ready_rows": 1})


def test_format_outbound_run_trust_report_includes_core_fields() -> None:
    run = {
        "schema_version": "1",
        "lane": "lead",
        "gmail_user": "contacto@origenlab.cl",
        "sqlite_path": "/data/db.sqlite",
        "sent_folders_resolved": ["[Gmail]/Enviados", "[Gmail]/Sent Mail"],
        "sent_folder_defaults_used": True,
        "strict_contact_graph_noise": False,
        "created_at_utc": "2026-04-15T12:00:00+00:00",
        "artifact_paths": {"marketing_csv": "/out/n.csv"},
        "counts": {"n_exported": 5},
    }
    text = format_outbound_run_trust_report(run)
    assert "lane:              lead" in text
    assert "gmail_user:        contacto@origenlab.cl" in text
    assert "sqlite_path:       /data/db.sqlite" in text
    assert "[Gmail]/Enviados" in text
    assert "n_exported: 5" in text
    assert "marketing_csv:" in text


def test_trust_report_from_summary_path_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "summary.json"
    p.write_text(
        json.dumps(
            {
                "outbound_run": {
                    "schema_version": "1",
                    "lane": "archive",
                    "gmail_user": "a@b.cl",
                    "sqlite_path": "/x.sqlite",
                    "sent_folders_resolved": ["[Gmail]/Enviados"],
                    "sent_folder_defaults_used": True,
                    "strict_contact_graph_noise": True,
                    "extra_exclude_domains": [],
                    "created_at_utc": "t",
                    "artifact_paths": {},
                    "counts": {"send_ready_rows": 2},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    text = trust_report_from_summary_path(p)
    assert "lane:              archive" in text
    assert "send_ready_rows: 2" in text


def test_print_outbound_run_summary_cli(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "outbound_run": {
                    "schema_version": "1",
                    "lane": "lead",
                    "gmail_user": "g@x.cl",
                    "sqlite_path": "/d.sqlite",
                    "sent_folders_resolved": [],
                    "sent_folder_defaults_used": True,
                    "strict_contact_graph_noise": False,
                    "extra_exclude_domains": [],
                    "created_at_utc": "t",
                    "artifact_paths": {},
                    "counts": {},
                }
            }
        ),
        encoding="utf-8",
    )
    script = REPO / "scripts" / "qa" / "print_outbound_run_summary.py"
    r = subprocess.run(
        [sys.executable, str(script), "--json", str(p)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "lane:              lead" in r.stdout


def test_load_summary_json_invalid_root(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_summary_json(p)
