"""Tests for dashboard snapshot publication to ops.pipeline_kv."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from origenlab_email_pipeline.dashboard_snapshot_publish import (
    ACTIVE_CURRENT_REDACTION,
    GMAIL_INTERACTION_AUDIT_KV_KEY,
    OPERATOR_AUTOMATION_STATUS_SNAPSHOT_KV_KEY,
    publish_operator_dashboard_snapshots,
    redact_automation_status_for_publish,
    upsert_pipeline_kv_snapshot,
)


def test_redact_automation_status_removes_local_paths() -> None:
    payload = {
        "active_current_dir": "/home/op/reports/out/active/current",
        "sqlite_path": "/home/op/data/emails.sqlite",
        "warnings": ["see /home/op/reports/out/active/current/manifest.json"],
        "verdict": "healthy",
    }
    redacted = redact_automation_status_for_publish(payload)
    assert redacted["active_current_dir"] == ACTIVE_CURRENT_REDACTION
    assert "sqlite_path" not in redacted
    assert "/home/op" not in json.dumps(redacted)


def test_upsert_pipeline_kv_dry_run_no_write() -> None:
    summary = upsert_pipeline_kv_snapshot(
        "postgresql://u:p@localhost/db",
        "test_key",
        {"ok": True},
        dry_run=True,
    )
    assert summary["dry_run"] is True
    assert summary["published"] is False


@patch("origenlab_email_pipeline.dashboard_snapshot_publish.psycopg")
@patch("origenlab_email_pipeline.dashboard_snapshot_publish.pg_table_exists", return_value=True)
def test_upsert_pipeline_kv_apply_writes(
    _table_exists: MagicMock,
    mock_psycopg: MagicMock,
) -> None:
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = ("2026-06-11T12:00:00+00:00",)
    conn.cursor.return_value.__enter__.return_value = cur
    mock_psycopg.connect.return_value.__enter__.return_value = conn

    summary = upsert_pipeline_kv_snapshot(
        "postgresql://u:p@localhost/db",
        GMAIL_INTERACTION_AUDIT_KV_KEY,
        {"domains": []},
        dry_run=False,
    )
    assert summary["published"] is True
    execute_args = cur.execute.call_args[0]
    assert execute_args[1][0] == GMAIL_INTERACTION_AUDIT_KV_KEY


@patch("origenlab_email_pipeline.dashboard_snapshot_publish.upsert_pipeline_kv_snapshot")
@patch(
    "origenlab_email_pipeline.dashboard_snapshot_publish.build_operator_automation_status_snapshot"
)
@patch(
    "origenlab_email_pipeline.dashboard_snapshot_publish.build_gmail_interaction_audit_snapshot"
)
def test_publish_bundle_dry_run_counts_only(
    mock_gmail: MagicMock,
    mock_auto: MagicMock,
    mock_upsert: MagicMock,
    tmp_path: Path,
) -> None:
    mock_gmail.return_value = {"domains": [{"domain": "ika.net.br"}], "lookback_days": 180}
    mock_auto.return_value = {"verdict": "healthy"}
    mock_upsert.side_effect = lambda _url, key, _val, dry_run: {
        "kv_key": key,
        "published": not dry_run,
        "dry_run": dry_run,
    }

    result = publish_operator_dashboard_snapshots(
        "postgresql://u:p@localhost/db",
        sqlite_path=tmp_path / "x.sqlite",
        active_current_dir=tmp_path / "active" / "current",
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["gmail_interaction_audit"]["domain_count"] == 1
    assert mock_upsert.call_count == 2
    keys = {call.args[1] for call in mock_upsert.call_args_list}
    assert keys == {
        GMAIL_INTERACTION_AUDIT_KV_KEY,
        OPERATOR_AUTOMATION_STATUS_SNAPSHOT_KV_KEY,
    }


@patch("origenlab_email_pipeline.dashboard_snapshot_publish.build_gmail_interaction_audit_snapshot")
def test_publish_requires_no_gmail_network(mock_gmail: MagicMock, tmp_path: Path) -> None:
    mock_gmail.return_value = {"domains": [], "lookback_days": 180}
    with patch(
        "origenlab_email_pipeline.dashboard_snapshot_publish.build_operator_automation_status_snapshot",
        return_value={"verdict": "attention"},
    ), patch(
        "origenlab_email_pipeline.dashboard_snapshot_publish.upsert_pipeline_kv_snapshot",
        return_value={"published": False, "dry_run": True},
    ):
        publish_operator_dashboard_snapshots(
            "postgresql://u:p@localhost/db",
            sqlite_path=tmp_path / "x.sqlite",
            active_current_dir=tmp_path / "active" / "current",
            dry_run=True,
        )
    mock_gmail.assert_called_once()
