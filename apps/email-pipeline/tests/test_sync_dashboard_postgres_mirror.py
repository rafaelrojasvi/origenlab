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

from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_PREFIX
from origenlab_email_pipeline.dashboard_postgres_sync import (
    DASHBOARD_SYNC_KV_KEY,
    EXPECTED_ALEMBIC_HEAD,
    assert_sqlite_mart_ready_for_mirror_sync,
    build_loader_command,
    collect_mirror_counts,
    format_summary_text,
    plan_loader_steps,
    redact_postgres_url,
    run_dashboard_mirror_sync,
    write_sync_watermark,
)
from origenlab_email_pipeline.db import init_schema

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sync" / "sync_dashboard_postgres_mirror.py"

_PATCH_PG = "origenlab_email_pipeline.dashboard_postgres_sync.preflight_postgres"
_PATCH_COUNTS = "origenlab_email_pipeline.dashboard_postgres_sync.collect_mirror_counts"
_PATCH_WM = "origenlab_email_pipeline.dashboard_postgres_sync.write_sync_watermark"
_PATCH_CLASSIFY = (
    "origenlab_email_pipeline.dashboard_postgres_sync.sync_email_classification_canonical"
)
_PATCH_PURCHASE = (
    "origenlab_email_pipeline.dashboard_postgres_sync.sync_commercial_purchase_events"
)


def _setup_sqlite(db_path: Path, *, with_mart_rows: bool) -> None:
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    conn.execute(
        """
        INSERT INTO emails (
          source_file, message_id, date_iso, folder, sender, recipients, subject, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{CONTACTO_GMAIL_SOURCE_PREFIX}INBOX/msg",
            "msg-1",
            "2026-05-16T10:00:00",
            "INBOX",
            "buyer@lab.cl",
            "contacto@origenlab.cl",
            "Test",
            "body",
        ),
    )
    if with_mart_rows:
        conn.execute("INSERT INTO contact_master (email) VALUES ('buyer@lab.cl')")
        conn.execute("INSERT INTO organization_master (domain) VALUES ('lab.cl')")
        conn.execute(
            """
            INSERT INTO opportunity_signals (
              signal_type, entity_kind, entity_key, created_at
            ) VALUES ('test', 'contact', 'buyer@lab.cl', '2026-05-16T10:00:00')
            """
        )
    conn.commit()
    conn.close()


def _sample_mirror_counts() -> dict[str, int]:
    return {
        "canonical_contact_count": 10,
        "canonical_organization_count": 5,
        "canonical_opportunity_signal_count": 3,
        "archive_contact_count": 100,
        "archive_organization_count": 50,
        "archive_opportunity_signal_count": 20,
        "email_suppression_count": 1,
        "domain_suppression_count": 1,
        "outreach_state_count": 2,
        "commercial_purchase_event_count": 1,
        "commercial_purchase_event_item_count": 3,
    }


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

    with patch(_PATCH_PG, return_value=(EXPECTED_ALEMBIC_HEAD, [])), patch(
        _PATCH_COUNTS,
        return_value=sample_counts,
    ), patch(_PATCH_WM) as mock_wm:
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
    _setup_sqlite(db, with_mart_rows=True)

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

    with patch(_PATCH_PG, return_value=(EXPECTED_ALEMBIC_HEAD, [])), patch(
        _PATCH_COUNTS,
        return_value=sample_counts,
    ), patch(_PATCH_WM, return_value=42), patch(
        _PATCH_CLASSIFY,
        return_value={"rows_written": 0, "skipped": False},
    ), patch(
        _PATCH_PURCHASE,
        return_value={"events_written": 0, "skipped": False},
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


def test_assert_sqlite_mart_fails_when_canonical_gmail_but_empty_mart(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _setup_sqlite(db, with_mart_rows=False)
    with pytest.raises(ValueError, match="contact_master") as exc:
        assert_sqlite_mart_ready_for_mirror_sync(db, allow_empty_mart=False)
    msg = str(exc.value)
    assert "organization_master" in msg
    assert "opportunity_signals" in msg
    assert "build_business_mart" in msg


def test_assert_sqlite_mart_passes_when_mart_has_rows(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _setup_sqlite(db, with_mart_rows=True)
    counts = assert_sqlite_mart_ready_for_mirror_sync(db, allow_empty_mart=False)
    assert counts.canonical_gmail_email_count == 1
    assert counts.mart_table_counts["contact_master"] == 1


def test_assert_sqlite_mart_allow_empty_mart_override(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _setup_sqlite(db, with_mart_rows=False)
    counts = assert_sqlite_mart_ready_for_mirror_sync(db, allow_empty_mart=True)
    assert counts.mart_table_counts["contact_master"] == 0


def test_sync_fails_when_canonical_gmail_but_empty_mart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "emails.sqlite"
    _setup_sqlite(db, with_mart_rows=False)
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    loader_calls: list[str] = []

    def _fake_loader(cmd: list[str], _root: Path) -> int:
        loader_calls.append(" ".join(cmd))
        return 0

    with patch(_PATCH_PG, return_value=(EXPECTED_ALEMBIC_HEAD, [])):
        result = run_dashboard_mirror_sync(
            ["--sqlite-db", str(db)],
            repo_root=REPO,
            loader_runner=_fake_loader,
        )

    assert result["ok"] is False
    assert loader_calls == []
    assert any("contact_master" in e for e in result["errors"])


def test_sync_passes_when_mart_tables_have_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "emails.sqlite"
    _setup_sqlite(db, with_mart_rows=True)
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    loader_calls: list[str] = []

    def _fake_loader(cmd: list[str], _root: Path) -> int:
        if "mart_core" in " ".join(cmd):
            loader_calls.append("mart")
        return 0

    with patch(_PATCH_PG, return_value=(EXPECTED_ALEMBIC_HEAD, [])), patch(
        _PATCH_COUNTS,
        return_value=_sample_mirror_counts(),
    ), patch(_PATCH_WM, return_value=7), patch(
        _PATCH_CLASSIFY,
        return_value={"rows_written": 0, "skipped": False},
    ), patch(
        _PATCH_PURCHASE,
        return_value={"events_written": 0, "skipped": False},
    ):
        result = run_dashboard_mirror_sync(
            ["--sqlite-db", str(db)],
            repo_root=REPO,
            loader_runner=_fake_loader,
        )

    assert result["ok"] is True
    assert "mart" in loader_calls
    assert "commercial_purchase_sync" in result


def test_sync_passes_with_allow_empty_mart_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "emails.sqlite"
    _setup_sqlite(db, with_mart_rows=False)
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    loader_calls: list[str] = []

    def _fake_loader(cmd: list[str], _root: Path) -> int:
        loader_calls.append("ran")
        return 0

    with patch(_PATCH_PG, return_value=(EXPECTED_ALEMBIC_HEAD, [])), patch(
        _PATCH_COUNTS,
        return_value=_sample_mirror_counts(),
    ), patch(_PATCH_WM, return_value=1), patch(
        _PATCH_CLASSIFY,
        return_value={"rows_written": 0, "skipped": False},
    ), patch(
        _PATCH_PURCHASE,
        return_value={"events_written": 0, "skipped": False},
    ):
        result = run_dashboard_mirror_sync(
            ["--sqlite-db", str(db), "--allow-empty-mart"],
            repo_root=REPO,
            loader_runner=_fake_loader,
        )

    assert result["ok"] is True
    assert len(loader_calls) == 2


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
    assert "--allow-empty-mart" in r.stdout


def test_alembic_migration_defines_dashboard_sync_run() -> None:
    path = REPO / "alembic" / "versions" / "20260517_0008_reporting_dashboard_sync_run.py"
    text = path.read_text(encoding="utf-8")
    assert "reporting.dashboard_sync_run" in text


def test_alembic_migration_defines_email_classification_canonical() -> None:
    path = REPO / "alembic" / "versions" / "20260518_0009_reporting_email_classification_canonical.py"
    text = path.read_text(encoding="utf-8")
    assert "reporting.email_classification_canonical" in text


def test_alembic_head_is_commercial_purchase_events() -> None:
    path = REPO / "alembic" / "versions" / "20260519_0010_commercial_purchase_events.py"
    text = path.read_text(encoding="utf-8")
    assert "commercial.purchase_event" in text
    assert EXPECTED_ALEMBIC_HEAD == "20260519_0010"
