"""Lead / client-pack provenance helpers (factual; no fake stack state)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.lead_provenance import (
    build_client_pack_provenance,
    build_operational_stack_manifest_payload,
    operational_stack_last_run_path,
    read_operational_run_id_from_env,
    read_operational_stack_last_run,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.operational_trust import verify_client_pack_against_db


def test_build_client_pack_provenance_without_stack_record(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    db.touch()
    prov = build_client_pack_provenance(
        repo_root=tmp_path,
        db_path_configured=None,
        db_path_resolved=db.resolve(),
        generated_at_utc="2026-01-01T00:00:00Z",
    )
    assert prov["schema_version"] == 2
    assert prov["generated_at_utc"] == "2026-01-01T00:00:00Z"
    assert prov["db_path"] is None
    assert prov["db_path_resolved"] == str(db.resolve())
    assert prov["operational_run_id"] is None
    assert prov["publish_gate_validated_this_artifact"] is False
    assert prov["operational_stack_last_run_present"] is False
    assert prov["upstream_reconcile_mode"] == "unknown"
    assert prov["publish_gate_skipped_in_last_stack"] is None
    assert prov["last_operational_stack"] is None
    assert "caveat" in prov


def test_build_client_pack_provenance_with_explicit_run_id(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    db.touch()
    prov = build_client_pack_provenance(
        repo_root=tmp_path,
        db_path_configured=None,
        db_path_resolved=db.resolve(),
        generated_at_utc="2026-01-01T00:00:00Z",
        operational_run_id="550e8400-e29b-41d4-a716-446655440000",
    )
    assert prov["operational_run_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert prov["publish_gate_validated_this_artifact"] is False
    assert "publish_gate.passed" in prov["caveat"]


def test_read_operational_run_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_LEADS_OPERATIONAL_RUN_ID", raising=False)
    assert read_operational_run_id_from_env() is None
    monkeypatch.setenv("ORIGENLAB_LEADS_OPERATIONAL_RUN_ID", "  rid-1  ")
    assert read_operational_run_id_from_env() == "rid-1"


def test_build_operational_stack_manifest_payload_skip_gate(tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    db.touch()
    p = build_operational_stack_manifest_payload(
        repo_root=tmp_path,
        run_id="r1",
        started_at_utc="2026-01-01T10:00:00Z",
        completed_at_utc="2026-01-01T11:00:00Z",
        reconcile_mode="apply",
        skip_fetch=True,
        skip_focus=False,
        skip_pack=False,
        skip_gate=True,
        publish_gate_exit_code=None,
        db_path_resolved=db.resolve(),
    )
    assert p["run_id"] == "r1"
    assert p["publish_gate"]["executed"] is False
    assert p["publish_gate"]["passed"] is None
    assert p["publish_gate"]["exit_code"] is None


def test_build_operational_stack_manifest_payload_gate_fail(tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    db.touch()
    p = build_operational_stack_manifest_payload(
        repo_root=tmp_path,
        run_id="r2",
        started_at_utc="2026-01-01T10:00:00Z",
        completed_at_utc="2026-01-01T11:00:00Z",
        reconcile_mode="apply",
        skip_fetch=False,
        skip_focus=False,
        skip_pack=False,
        skip_gate=False,
        publish_gate_exit_code=1,
        db_path_resolved=db.resolve(),
    )
    assert p["publish_gate"]["executed"] is True
    assert p["publish_gate"]["passed"] is False
    assert p["publish_gate"]["exit_code"] == 1


def test_read_operational_stack_round_trip(tmp_path: Path) -> None:
    p = operational_stack_last_run_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": 1,
        "completed_at_utc": "2026-02-02T12:00:00Z",
        "reconcile_mode": "apply",
        "skipped": {"publish_gate": False},
    }
    p.write_text(json.dumps(body), encoding="utf-8")
    got = read_operational_stack_last_run(tmp_path)
    assert got == body
    ydb = tmp_path / "y.sqlite"
    ydb.touch()
    prov = build_client_pack_provenance(
        repo_root=tmp_path,
        db_path_configured="/x.sqlite",
        db_path_resolved=ydb.resolve(),
        generated_at_utc="2026-01-01T00:00:00Z",
    )
    assert prov["operational_stack_last_run_present"] is True
    assert prov["upstream_reconcile_mode"] == "apply"
    assert prov["publish_gate_skipped_in_last_stack"] is False
    assert prov["last_operational_stack"]["completed_at_utc"] == "2026-02-02T12:00:00Z"


def test_verify_provenance_db_mismatch_non_critical(tmp_path: Path) -> None:
    """Session DB must match summary provenance when provenance block is present."""
    pack = tmp_path / "client_pack_latest"
    pack.mkdir(parents=True)
    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    for p in (db_a, db_b):
        p.touch()
        conn = sqlite3.connect(str(p))
        try:
            ensure_leads_tables(conn)
            conn.execute(
                """
                INSERT INTO lead_master (
                  source_name, source_record_id, org_name, fit_bucket, priority_score, status
                ) VALUES ('s', '1', 'O', 'high_fit', 1.0, 'nuevo')
                """
            )
            conn.commit()
        finally:
            conn.close()

    summary = {
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "totals": {"lead_master_rows": 1, "fit_bucket": {"high_fit": 1}},
        "provenance": {
            "db_path_resolved": str(db_a.resolve()),
        },
    }
    (pack / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    checks = verify_client_pack_against_db(pack / "summary.json", db_b.resolve())
    ids = [c.check_id for c in checks]
    assert "pack_summary_provenance_db_matches_session" in ids
    prov_chk = next(c for c in checks if c.check_id == "pack_summary_provenance_db_matches_session")
    assert prov_chk.ok is False
    assert prov_chk.critical is False
