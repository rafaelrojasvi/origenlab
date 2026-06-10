"""Tests for email_mart_features backfill CLI and helper."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from origenlab_email_pipeline.core.mart.build_email_mart_features_cli import (
    print_email_mart_features_backfill_report,
    run_build_email_mart_features_from_argv,
    run_email_mart_features_backfill,
)
from origenlab_email_pipeline.db import init_schema

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_SCRIPT = REPO / "scripts" / "mart" / "build_email_mart_features.py"
_INTERNAL = frozenset({"origenlab.cl"})
_COMPUTED_AT = "2026-06-10T12:00:00+00:00"
_SLACK_DAYS = 30


def _insert_email(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    subject: str = "Subject",
    sender: str = "Buyer <buyer@lab.cl>",
    recipients: str = "contacto@origenlab.cl",
    top_reply_clean: str = "top body",
    full_body_clean: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO emails (
          source_file, message_id, date_iso, folder, sender, recipients,
          subject, body, full_body_clean, top_reply_clean
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "gmail:contacto@origenlab.cl/INBOX",
            message_id,
            datetime.now(timezone.utc).date().isoformat(),
            "INBOX",
            sender,
            recipients,
            subject,
            top_reply_clean or full_body_clean or "",
            full_body_clean,
            top_reply_clean,
        ),
    )
    return int(cur.lastrowid)


def _seed_db(db: Path, *, email_count: int = 2) -> None:
    conn = sqlite3.connect(db)
    init_schema(conn)
    for i in range(email_count):
        _insert_email(conn, message_id=f"msg-{i}", top_reply_clean=f"body {i}")
    conn.commit()
    conn.close()


def _feature_count(db: Path) -> int:
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM email_mart_features").fetchone()[0]
    conn.close()
    return int(count)


def _run_script(db: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(_SRC), "ORIGENLAB_SQLITE_PATH": str(db)}
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_build_email_mart_features_cli_runner_importable() -> None:
    assert callable(run_build_email_mart_features_from_argv)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db)

    conn = sqlite3.connect(db)
    report = run_email_mart_features_backfill(
        conn,
        dry_run=True,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    conn.close()

    assert report.dry_run is True
    assert report.scanned_emails == 2
    assert report.missing_features == 2
    assert report.stale_features == 0
    assert report.current_features == 0
    assert report.inserted_features == 0
    assert report.updated_features == 0
    assert _feature_count(db) == 0


def test_apply_inserts_missing_feature_rows(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db, email_count=2)

    conn = sqlite3.connect(db)
    report = run_email_mart_features_backfill(
        conn,
        dry_run=False,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    conn.close()

    assert report.inserted_features == 2
    assert report.updated_features == 0
    assert _feature_count(db) == 2


def test_second_apply_skips_current_rows(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db, email_count=2)

    conn = sqlite3.connect(db)
    run_email_mart_features_backfill(
        conn,
        dry_run=False,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    second = run_email_mart_features_backfill(
        conn,
        dry_run=False,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    conn.close()

    assert second.current_features == 2
    assert second.missing_features == 0
    assert second.stale_features == 0
    assert second.inserted_features == 0
    assert second.updated_features == 0


def test_stale_row_updates_on_apply(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db, email_count=1)

    conn = sqlite3.connect(db)
    run_email_mart_features_backfill(
        conn,
        dry_run=False,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    conn.execute("UPDATE emails SET subject = 'Changed subject' WHERE message_id = 'msg-0'")
    conn.commit()
    second = run_email_mart_features_backfill(
        conn,
        dry_run=False,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at="2026-06-10T13:00:00+00:00",
    )
    row = conn.execute(
        "SELECT feature_source_hash, computed_at FROM email_mart_features WHERE email_id = 1"
    ).fetchone()
    conn.close()

    assert second.stale_features == 1
    assert second.updated_features == 1
    assert row is not None
    assert row[1] == "2026-06-10T13:00:00+00:00"


def test_limit_limits_scanned_rows(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db, email_count=3)

    conn = sqlite3.connect(db)
    report = run_email_mart_features_backfill(
        conn,
        dry_run=True,
        limit=2,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    conn.close()

    assert report.scanned_emails == 2


def test_backfill_report_output_includes_expected_counters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from origenlab_email_pipeline.core.mart.build_email_mart_features_cli import (
        EmailMartFeaturesBackfillReport,
    )

    print_email_mart_features_backfill_report(
        EmailMartFeaturesBackfillReport(
            dry_run=True,
            scanned_emails=2,
            existing_features=0,
            missing_features=2,
            stale_features=0,
            current_features=0,
            inserted_features=0,
            updated_features=0,
            elapsed_seconds=0.12,
            body_total_chars=16,
        )
    )
    out = capsys.readouterr().out
    assert "email_mart_features dry_run=true" in out
    assert "scanned_emails=2" in out
    assert "missing_features=2" in out
    assert "elapsed_seconds=0.12" in out
    assert "body_total_chars=16" in out


def test_script_defaults_to_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db)
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))

    cp = _run_script(db)
    assert cp.returncode == 0, cp.stderr
    assert "email_mart_features dry_run=true" in cp.stdout
    assert "missing_features=2" in cp.stdout
    assert _feature_count(db) == 0


def test_script_apply_writes_rows(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_db(db)

    cp = _run_script(db, "--apply", "--internal-domain", "origenlab.cl")
    assert cp.returncode == 0, cp.stderr
    assert "email_mart_features dry_run=false" in cp.stdout
    assert "inserted_features=2" in cp.stdout
    assert _feature_count(db) == 2


def test_origenlab_subcommand_maps_to_script() -> None:
    from origenlab_email_pipeline.operator_cli.constants import SUBCOMMAND_SCRIPTS

    assert (
        SUBCOMMAND_SCRIPTS["build-email-mart-features"]
        == "scripts/mart/build_email_mart_features.py"
    )
