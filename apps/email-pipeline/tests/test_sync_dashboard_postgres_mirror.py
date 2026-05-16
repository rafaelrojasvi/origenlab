"""Tests for dashboard Postgres mirror sync orchestration."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from origenlab_email_pipeline.dashboard_postgres_sync import (
    DASHBOARD_SYNC_KV_KEY,
    EXPECTED_ALEMBIC_HEAD,
    build_loader_command,
    collect_mirror_counts,
    format_summary_text,
    plan_loader_steps,
    redact_postgres_url,
    run_dashboard_mirror_sync,
    write_sync_watermark,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sync" / "sync_dashboard_postgres_mirror.py"


def test_redact_postgres_url_strips_password() -> None:
    url = "postgresql://origenlab:secret@127.0.0.1:5432/origenlab_scratch"
    red = redact_postgres_url(url)
    assert "secret" not in red
    assert "origenlab:***" in red
    assert "origenlab_scratch" in red


def test_plan_loader_steps_default_order() -> None:
    steps = plan_loader_steps(only=None, skip_outbound=False, skip_mart=False)
    assert [s.name for s in steps] == ["outbound_sidecars", "mart_core"]
    assert steps[1].argv == ("--replace", "--tables", "all")


def test_plan_loader_steps_only_canonical() -> None:
    steps = plan_loader_steps(only="canonical", skip_outbound=False, skip_mart=False)
    assert len(steps) == 1
    assert steps[0].name == "mart_core"
    assert "--tables" in steps[0].argv
    assert "canonical" in steps[0].argv


def test_refuses_missing_postgres_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    db.write_bytes(b"")
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))
    result = run_dashboard_mirror_sync(
        ["--sqlite-db", str(db)],
        repo_root=REPO,
        loader_runner=lambda _c, _r: 0,
    )
    assert result["ok"] is False
    assert any("Postgres URL required" in e for e in result["errors"])


def test_dry_run_does_not_invoke_loaders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    calls: list[list[str]] = []

    def _fake_loader(cmd: list[str], _root: Path) -> int:
        calls.append(cmd)
        return 0

    sample_counts = {
        "canonical_contact_count": 497,
        "archive_contact_count": 27198,
        "canonical_organization_count": 261,
        "archive_organization_count": 10688,
        "canonical_opportunity_signal_count": 200,
        "archive_opportunity_signal_count": 2705,
        "email_suppression_count": 2,
        "domain_suppression_count": 1,
        "outreach_state_count": 4,
    }

    with patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.preflight_postgres",
        return_value=(EXPECTED_ALEMBIC_HEAD, []),
    ), patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.collect_mirror_counts",
        return_value=sample_counts,
    ), patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.write_sync_watermark",
    ) as mock_wm:
        result = run_dashboard_mirror_sync(
            ["--sqlite-db", str(db), "--dry-run"],
            repo_root=REPO,
            loader_runner=_fake_loader,
        )

    assert result["ok"] is True
    assert result["status"] == "dry_run"
    assert result["counts"]["canonical_contact_count"] == 497
    assert result["counts"]["archive_contact_count"] == 27198
    assert calls == []
    mock_wm.assert_not_called()


def test_loaders_called_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("SELECT 1")
    conn.close()

    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    order: list[str] = []

    def _fake_loader(cmd: list[str], _root: Path) -> int:
        if "outbound_sidecars" in " ".join(cmd):
            order.append("outbound")
        if "mart_core" in " ".join(cmd):
            order.append("mart")
        return 0

    sample_counts = {f"k{i}": i for i in range(9)}
    keys = [
        "canonical_contact_count",
        "canonical_organization_count",
        "canonical_opportunity_signal_count",
        "archive_contact_count",
        "archive_organization_count",
        "archive_opportunity_signal_count",
        "email_suppression_count",
        "domain_suppression_count",
        "outreach_state_count",
    ]
    sample_counts = dict(zip(keys, [1, 2, 3, 4, 5, 6, 7, 8, 9], strict=True))

    with patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.preflight_postgres",
        return_value=(EXPECTED_ALEMBIC_HEAD, []),
    ), patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.collect_mirror_counts",
        return_value=sample_counts,
    ), patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.write_sync_watermark",
        return_value=42,
    ), patch(
        "origenlab_email_pipeline.dashboard_postgres_sync.sync_email_classification_canonical",
        return_value={"rows_written": 0, "skipped": False},
    ):
        result = run_dashboard_mirror_sync(
            ["--sqlite-db", str(db)],
            repo_root=REPO,
            loader_runner=_fake_loader,
        )

    assert result["ok"] is True
    assert order == ["outbound", "mart"]
    assert result["sync_run_id"] == 42


def test_summary_includes_canonical_and_archive_counts() -> None:
    text = format_summary_text(
        {
            "status": "success",
            "dry_run": False,
            "elapsed_seconds": 1.2,
            "counts": {
                "canonical_contact_count": 497,
                "archive_contact_count": 27198,
                "canonical_organization_count": 261,
                "archive_organization_count": 10688,
                "canonical_opportunity_signal_count": 200,
                "archive_opportunity_signal_count": 2705,
                "email_suppression_count": 3,
                "domain_suppression_count": 2,
                "outreach_state_count": 10,
            },
        }
    )
    assert "canonical:" in text
    assert "497" in text
    assert "27198" in text
    assert "dashboard/summary" in text


def test_write_sync_watermark_inserts_run_and_kv() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = (99,)

    class _Ctx:
        def __enter__(self) -> MagicMock:
            return cur

        def __exit__(self, *args: object) -> None:
            return None

    conn = MagicMock()
    conn.cursor.return_value = _Ctx()
    conn.__enter__ = lambda s: conn
    conn.__exit__ = lambda s, *a: None

    counts = {
        "canonical_contact_count": 1,
        "canonical_organization_count": 2,
        "canonical_opportunity_signal_count": 3,
        "archive_contact_count": 4,
        "archive_organization_count": 5,
        "archive_opportunity_signal_count": 6,
        "email_suppression_count": 7,
        "domain_suppression_count": 8,
        "outreach_state_count": 9,
    }

    with (
        patch("origenlab_email_pipeline.dashboard_postgres_sync.psycopg") as mock_pg,
        patch(
            "origenlab_email_pipeline.dashboard_postgres_sync.pg_table_exists",
            return_value=True,
        ),
    ):
        mock_pg.connect.return_value = conn
        from datetime import datetime, timezone

        sync_id = write_sync_watermark(
            "postgresql://u:p@127.0.0.1/scratch",
            sqlite_path=Path("/data/emails.sqlite"),
            postgres_url_redacted="postgresql://u:***@127.0.0.1/scratch",
            status="success",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            counts=counts,
            error_message=None,
            details={"loader_steps": []},
            dry_run=False,
        )

    assert sync_id == 99
    executed = " ".join(str(c) for c in cur.execute.call_args_list)
    assert "reporting.dashboard_sync_run" in executed
    assert DASHBOARD_SYNC_KV_KEY in executed


def test_build_loader_command_includes_replace() -> None:
    from origenlab_email_pipeline.dashboard_postgres_sync import LoaderStep

    step = LoaderStep("mart_core", "scripts/migrate/sqlite_mart_core_to_postgres.py", ("--replace",))
    cmd = build_loader_command(
        REPO,
        step,
        sqlite_path=Path("/tmp/x.sqlite"),
        postgres_url="postgresql://u:p@127.0.0.1/scratch",
        allow_non_scratch=False,
    )
    assert "--replace" in cmd
    assert str(Path("/tmp/x.sqlite")) in cmd


def test_script_help() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0
    assert "--dry-run" in r.stdout
    assert "--only" in r.stdout


def test_alembic_migration_defines_dashboard_sync_run() -> None:
    path = REPO / "alembic" / "versions" / "20260517_0008_reporting_dashboard_sync_run.py"
    text = path.read_text(encoding="utf-8")
    assert "reporting.dashboard_sync_run" in text


def test_alembic_migration_defines_email_classification_canonical() -> None:
    path = REPO / "alembic" / "versions" / "20260518_0009_reporting_email_classification_canonical.py"
    text = path.read_text(encoding="utf-8")
    assert "reporting.email_classification_canonical" in text
    assert EXPECTED_ALEMBIC_HEAD in text
