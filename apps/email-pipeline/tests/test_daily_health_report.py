"""Tests for read-only daily health report."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from origenlab_email_pipeline.qa import daily_health_report as dhr
from origenlab_email_pipeline.qa.daily_health_report import (
    SCHEMA_VERSION,
    build_daily_health_report,
    classify_daily_health,
)


def test_classify_ready_when_clean() -> None:
    verdict, reasons = classify_daily_health(
        collection_errors=[],
        operator_verdict="READY",
        mirror_file_ok=True,
        postgres_live_ok=True,
        net_new_ndr=0,
        falta_email_stale_display=0,
        operator_caution_is_review=False,
    )
    assert verdict == "READY"
    assert reasons == []


def test_classify_review_needed_ndr_backlog() -> None:
    verdict, reasons = classify_daily_health(
        collection_errors=[],
        operator_verdict="READY",
        mirror_file_ok=True,
        postgres_live_ok=True,
        net_new_ndr=3,
        falta_email_stale_display=0,
    )
    assert verdict == "REVIEW_NEEDED"
    assert any("net_new_ndr" in r for r in reasons)


def test_classify_review_needed_falta_stale() -> None:
    verdict, _ = classify_daily_health(
        collection_errors=[],
        operator_verdict="READY",
        mirror_file_ok=True,
        postgres_live_ok=True,
        net_new_ndr=0,
        falta_email_stale_display=2,
    )
    assert verdict == "REVIEW_NEEDED"


def test_classify_blocked_mirror_and_operator() -> None:
    verdict, reasons = classify_daily_health(
        collection_errors=[],
        operator_verdict="BLOCKED",
        mirror_file_ok=False,
        postgres_live_ok=False,
        net_new_ndr=5,
        falta_email_stale_display=1,
    )
    assert verdict == "BLOCKED"
    assert "operator_status=BLOCKED" in reasons


def test_classify_blocked_postgres_parity() -> None:
    verdict, reasons = classify_daily_health(
        collection_errors=[],
        operator_verdict="READY",
        mirror_file_ok=True,
        postgres_live_ok=False,
        net_new_ndr=0,
        falta_email_stale_display=0,
    )
    assert verdict == "BLOCKED"
    assert any("parity" in r for r in reasons)


def test_classify_blocked_collection_errors() -> None:
    verdict, reasons = classify_daily_health(
        collection_errors=["sqlite missing"],
        operator_verdict="READY",
        mirror_file_ok=True,
        postgres_live_ok=True,
        net_new_ndr=0,
        falta_email_stale_display=0,
    )
    assert verdict == "BLOCKED"
    assert reasons == ["sqlite missing"]


def test_summary_json_schema_fields(tmp_path: Path) -> None:
    result = dhr.DailyHealthReportResult(
        schema_version=SCHEMA_VERSION,
        generated_at="2026-06-02T12:00:00+00:00",
        date_label="2026_06_02",
        since_days=2,
        health_verdict="REVIEW_NEEDED",
        health_reasons=["net_new_ndr_backlog=1"],
        sqlite_path=str(tmp_path / "x.db"),
        ndr={"net_new_count": 1},
        suppression_outreach={"bounce_suppressions": 0},
        operator_status={"verdict": "READY"},
        mirror={"file_verifiers": {}},
        prospectos={"falta_email_stale_display_count": 0},
        post_send_digest={"found": False},
    )
    body = result.to_summary_dict()
    for key in (
        "schema_version",
        "generated_at",
        "date_label",
        "since_days",
        "health_verdict",
        "health_reasons",
        "sqlite_path",
        "ndr",
        "suppression_outreach",
        "operator_status",
        "mirror",
        "prospectos",
        "post_send_digest",
        "collection_errors",
    ):
        assert key in body
    assert body["schema_version"] == SCHEMA_VERSION


def test_build_daily_health_report_no_mutation_paths(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT, folder TEXT, subject TEXT, sender TEXT,
            date_iso TEXT, body TEXT, body_text_clean TEXT, full_body_clean TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    active = tmp_path / "active"
    active.mkdir()
    (active / "manifest.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "out"

    forbidden = [
        "origenlab_email_pipeline.contact_email_suppression.upsert_contact_email_suppression",
        "origenlab_email_pipeline.campaigns.post_send_digest.build_post_send_digest",
    ]
    patches = [patch(name) for name in forbidden]
    started = [p.start() for p in patches]
    try:
        with (
            patch.object(dhr, "build_operator_status_report") as mock_op,
            patch.object(dhr, "run_prospectos_safety_drift_audit") as mock_drift,
            patch.object(dhr, "scan_ndr_planned_recipients", return_value=({}, 0, 0)),
            patch.object(dhr, "summarize_ndr_backlog", return_value={"net_new_count": 0, "net_new_rows": []}),
            patch.object(dhr, "collect_falta_email_stale_display_rows", return_value=([], {"falta_email_stale_display_count": 0})),
            patch.object(dhr, "connect_sqlite_readonly", wraps=dhr.connect_sqlite_readonly),
        ):
            mock_op.return_value = MagicMock(
                verdict="READY",
                warnings=[],
                errors=[],
                postgres={},
                outbound_readiness={},
            )
            mock_drift.return_value = MagicMock(summary={"mismatches_count": 0})
            build_daily_health_report(
                repo_root=tmp_path,
                sqlite_path=db,
                active_current=active,
                manifest_path=active / "manifest.json",
                out_dir=out,
                skip_postgres=True,
            )
            for mock in started:
                mock.assert_not_called()
    finally:
        for p in patches:
            p.stop()


def test_falta_email_stale_detection(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE lead_research_prospect (
            prospect_key TEXT PRIMARY KEY,
            organization_name TEXT,
            contact_name TEXT,
            email TEXT,
            domain TEXT,
            classification TEXT,
            status TEXT,
            is_blocked INTEGER,
            is_active INTEGER,
            source_type TEXT,
            dataset_label TEXT,
            campaign_bucket TEXT,
            block_or_review_reason TEXT,
            gmail_first_contacted_at TEXT,
            gmail_last_contacted_at TEXT,
            gmail_sent_count INTEGER,
            gmail_received_count INTEGER
        );
        CREATE TABLE outreach_contact_state (
            contact_email_norm TEXT PRIMARY KEY,
            state TEXT,
            source TEXT,
            first_contacted_at TEXT,
            last_contacted_at TEXT
        );
        INSERT INTO lead_research_prospect VALUES (
            'k1','Org','',NULL,'example.org',
            'research_only_contact_needed','research_only_contact_needed',0,1,
            't','d','','','',NULL,0,0
        );
        INSERT INTO outreach_contact_state VALUES (
            'other@example.org','contacted','test',NULL,NULL
        );
        """
    )
    conn.commit()
    conn.close()
    conn = sqlite3.connect(db)
    rows, counts = dhr.collect_falta_email_stale_display_rows(conn)
    conn.close()
    assert counts["falta_email_stale_display_count"] == 1
    assert rows[0]["prospect_key"] == "k1"


def test_exit_code_fail_on_blocked() -> None:
    blocked = dhr.DailyHealthReportResult(
        schema_version=SCHEMA_VERSION,
        generated_at="t",
        date_label="d",
        since_days=2,
        health_verdict="BLOCKED",
        health_reasons=[],
        sqlite_path="x",
    )
    assert dhr.exit_code_for_result(blocked, fail_on_blocked=True) == 2
    assert dhr.exit_code_for_result(blocked, fail_on_blocked=False) == 1
    review = dhr.DailyHealthReportResult(
        schema_version=SCHEMA_VERSION,
        generated_at="t",
        date_label="d",
        since_days=2,
        health_verdict="REVIEW_NEEDED",
        health_reasons=[],
        sqlite_path="x",
    )
    assert dhr.exit_code_for_result(review, fail_on_blocked=False) == 1


def test_verifier_json_ok_render_dashboard_shape() -> None:
    assert dhr._verifier_json_ok(
        {"render_dashboard_assertions": {"passed": True, "failures": []}}
    )
    assert not dhr._verifier_json_ok(
        {"render_dashboard_assertions": {"passed": False, "failures": ["x"]}}
    )


def test_load_verifier_json_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vf = tmp_path / "outbound.json"
    vf.write_text(json.dumps({"ok": False, "errors": ["stale"]}), encoding="utf-8")
    monkeypatch.setattr(
        dhr,
        "VERIFIER_JSON_CANDIDATES",
        (("outbound_sidecar_mirror", vf),),
    )
    status = dhr.load_verifier_json_status()
    assert status["aggregate_ok"] is False
    assert status["verifiers"]["outbound_sidecar_mirror"]["ok"] is False
