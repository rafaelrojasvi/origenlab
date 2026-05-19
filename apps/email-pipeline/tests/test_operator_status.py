"""Tests for read-only operator status report."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.operator_status_report import (
    build_operator_status_report,
    compute_verdict,
    load_manifest,
)


def test_compute_verdict_blocked_without_sqlite() -> None:
    assert (
        compute_verdict(
            sqlite_exists=False,
            readiness_verdict="ready",
            manifest_warnings=[],
            extra_errors=[],
        )
        == "BLOCKED"
    )


def test_compute_verdict_caution_with_manifest_warnings() -> None:
    assert (
        compute_verdict(
            sqlite_exists=True,
            readiness_verdict="ready",
            manifest_warnings=["FastLab pending"],
            extra_errors=[],
        )
        == "CAUTION"
    )


def test_build_operator_status_report_minimal_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            date_iso TEXT,
            source_file TEXT,
            subject TEXT,
            folder TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO emails (date_iso, source_file, subject, folder) VALUES (?, ?, ?, ?)",
        (
            "2026-05-18T12:00:00-04:00",
            "gmail:contacto@origenlab.cl/[Gmail]/Enviados",
            "test",
            "[Gmail]/Enviados",
        ),
    )
    conn.commit()
    conn.close()

    active = tmp_path / "current"
    active.mkdir()
    manifest = {
        "known_warnings": ["test warning from manifest"],
        "canonical_files": [],
    }
    (active / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = build_operator_status_report(
        sqlite_path=db,
        active_current=active,
        manifest_path=active / "manifest.json",
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    assert report.sqlite_exists
    assert report.sent.get("canonical_sent_row_count") == 1
    assert "test warning from manifest" in report.warnings
    assert report.verdict in ("READY", "CAUTION", "BLOCKED")


def test_load_manifest_missing() -> None:
    assert load_manifest(Path("/nonexistent/manifest.json")) == {}


def test_operator_status_surfaces_manifest_and_parked_infra(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, date_iso TEXT, source_file TEXT, folder TEXT)"
    )
    conn.commit()
    conn.close()

    active = tmp_path / "current"
    active.mkdir()
    manifest = {
        "known_warnings": [
            "FastLab (contacto@fastlab.cl): manual_state_only_pending_sent_verification",
            "buyer_opportunity_crosscheck_20260518.csv is stale",
        ],
        "canonical_files": ["equipment_first_operator_queue_20260518.csv"],
        "postgres_status": "parked",
        "api_status": "parked",
        "stale_files": [{"path": "buyer_opportunity_crosscheck_20260518.csv"}],
    }
    (active / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (active / "equipment_first_operator_queue_20260518.csv").write_text(
        "priority_rank,codigo_licitacion\n1,TEST-1\n",
        encoding="utf-8",
    )

    report = build_operator_status_report(
        sqlite_path=db,
        active_current=active,
        manifest_path=active / "manifest.json",
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    assert report.verdict in ("CAUTION", "BLOCKED")  # BLOCKED if minimal schema fails readiness
    assert any("FastLab" in w for w in report.warnings)
    assert report.postgres.get("status") == "parked"
    assert report.api.get("status") == "parked"
    assert any("FastLab" in w for w in report.warnings)
    assert any("crosscheck" in w.lower() or "stale" in w.lower() for w in report.warnings)
    assert "equipment_first_operator_queue_20260518.csv" in report.canonical_files


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "reports/out/active/current/manifest.json").is_file(),
    reason="workspace manifest not present",
)
def test_operator_status_against_repo_manifest() -> None:
    repo = Path(__file__).resolve().parents[1]
    active = repo / "reports/out/active/current"
    manifest_path = active / "manifest.json"
    from origenlab_email_pipeline.config import load_settings

    db = load_settings().resolved_sqlite_path()
    if not db.is_file():
        pytest.skip("production SQLite not available")

    report = build_operator_status_report(
        sqlite_path=db,
        active_current=active,
        manifest_path=manifest_path,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    assert report.postgres.get("status") in ("parked", "available")
    assert report.api.get("status") == "parked"
    assert any("fastlab" in w.lower() for w in report.warnings)
    assert report.verdict in ("READY", "CAUTION", "BLOCKED")
    eq = report.equipment_queue.get("row_count")
    if (active / "equipment_first_operator_queue_20260518.csv").is_file():
        assert eq is not None and eq >= 1
