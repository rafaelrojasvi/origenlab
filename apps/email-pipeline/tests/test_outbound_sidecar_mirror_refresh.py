"""Tests for outbound sidecar mirror verification and refresh script wiring."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import textwrap
from pathlib import Path

import pytest

from origenlab_email_pipeline.outbound_sidecar_mirror_verify import (
    compare_outbound_sidecar_mirror,
    count_contacted_exact_csv_rows,
    sqlite_outbound_sidecar_counts,
)

_REPO = Path(__file__).resolve().parents[1]
_REFRESH = _REPO / "scripts/ops/refresh_render_dashboard_once.sh"
_OUTBOUND_HELPER = _REPO / "scripts/ops/_refresh_outbound_sidecar_mirror.sh"


def _script_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _make_sidecar_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY,
          suppression_reason_code TEXT NOT NULL,
          suppression_reason_text TEXT,
          suppression_source TEXT,
          last_bounced_at TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          first_contacted_at TEXT,
          last_contacted_at TEXT,
          source TEXT,
          notes TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT,
          lead_id INTEGER
        );
        INSERT INTO contact_email_suppression VALUES
          ('a@x.com', 'bounce_no_such_user', '', '', '', '2026-01-01T00:00:00Z', 'test'),
          ('b@x.com', 'manual_do_not_contact', '', '', '', '2026-01-01T00:00:00Z', 'test');
        INSERT INTO outreach_contact_state VALUES
          ('c@x.com', 'contacted', '', '', '', '', '2026-01-01T00:00:00Z', 'test', NULL);
        """
    )
    conn.close()


def test_sqlite_outbound_sidecar_counts_bounce_and_contacted(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    _make_sidecar_db(db)
    conn = sqlite3.connect(str(db))
    try:
        counts = sqlite_outbound_sidecar_counts(conn)
    finally:
        conn.close()
    assert counts["email_suppression_total"] == 2
    assert counts["bounce_suppressions"] == 1
    assert counts["outreach_contacted"] == 1
    assert counts["contacted_sidecar_distinct_emails"] == 3


def test_compare_outbound_sidecar_mirror_detects_stale_suppressions() -> None:
    sqlite_counts = {
        "email_suppression_total": 114,
        "bounce_suppressions": 30,
        "domain_suppression_total": 0,
        "outreach_state_total": 50,
        "outreach_contacted": 40,
        "contacted_sidecar_distinct_emails": 120,
    }
    postgres_counts = dict(sqlite_counts)
    postgres_counts["email_suppression_total"] = 96
    postgres_counts["bounce_suppressions"] = 12

    report = compare_outbound_sidecar_mirror(sqlite_counts, postgres_counts)
    assert report["ok"] is False
    assert any("email_suppression_total" in e for e in report["errors"])
    assert any("bounce_suppressions" in e for e in report["errors"])


def test_compare_outbound_sidecar_mirror_ok_when_counts_match() -> None:
    counts = {
        "email_suppression_total": 114,
        "bounce_suppressions": 30,
        "domain_suppression_total": 1,
        "outreach_state_total": 50,
        "outreach_contacted": 40,
        "contacted_sidecar_distinct_emails": 120,
    }
    report = compare_outbound_sidecar_mirror(counts, dict(counts))
    assert report["ok"] is True
    assert report["errors"] == []


def test_count_contacted_exact_csv_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "contacted_exact_emails_for_exclusion.csv"
    csv_path.write_text(
        "normalized_email,source\n"
        "a@x.com,sent\n"
        "b@x.com,outreach\n",
        encoding="utf-8",
    )
    assert count_contacted_exact_csv_rows(csv_path) == 2
    assert count_contacted_exact_csv_rows(tmp_path / "missing.csv") is None


def test_refresh_script_defaults_outbound_sidecar_mirror_on() -> None:
    text = _script_text(_REFRESH)
    assert 'RUN_OUTBOUND_SIDECAR_MIRROR="${RUN_OUTBOUND_SIDECAR_MIRROR:-1}"' in text
    assert 'RUN_OUTBOUND_SIDECAR_MIRROR" == "1"' in text
    assert "OUTBOUND_SIDECAR_MIRROR_STATUS" in text


def test_refresh_script_runs_sidecar_sync_after_lead_research_mirror() -> None:
    text = _script_text(_REFRESH)
    lead_pos = text.index('RUN_LEAD_RESEARCH_MIRROR" == "1"')
    sidecar_pos = text.index('RUN_OUTBOUND_SIDECAR_MIRROR" == "1"')
    assert sidecar_pos > lead_pos


def test_refresh_script_when_outbound_enabled_runs_replace_and_verify() -> None:
    text = _script_text(_REFRESH) + _script_text(_OUTBOUND_HELPER)
    assert "sqlite_outbound_sidecars_to_postgres.py --replace" in text
    assert "verify_outbound_sidecar_postgres_mirror.py" in text
    assert "/tmp/outbound_sidecar_mirror_verify.json" in text
    assert "email_suppression_total" in text


def test_outbound_helper_verify_failure_message_and_exit() -> None:
    text = _script_text(_OUTBOUND_HELPER)
    assert "Outbound sidecar mirror verify failed" in text
    assert "PRECAUCIÓN" in text
    assert "return 1" in text


def test_outbound_helper_failure_stops_with_nonzero_exit(tmp_path: Path) -> None:
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    uv_stub = stub_bin / "uv"
    uv_stub.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -eo pipefail
            if [[ "$1" == "run" && "$2" == "python" ]]; then
              script="${3:-}"
              if [[ "$script" == *verify_outbound_sidecar_postgres_mirror.py* ]]; then
                exit 1
              fi
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    uv_stub.chmod(0o755)

    runner = tmp_path / "run_outbound.sh"
    runner.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -eo pipefail
            export PATH="{stub_bin}:$PATH"
            export ORIGENLAB_SQLITE_PATH="{tmp_path / 'emails.sqlite'}"
            # shellcheck source=scripts/ops/_refresh_outbound_sidecar_mirror.sh
            source "{_OUTBOUND_HELPER}"
            run_outbound_sidecar_mirror_refresh "{_REPO}" "{tmp_path / 'verify.json'}" 0
            """
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)

    cp = subprocess.run(
        ["bash", str(runner)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PATH": f"{stub_bin}:{os.environ.get('PATH', '')}"},
    )
    assert cp.returncode == 1
    assert "Outbound sidecar mirror verify failed" in cp.stderr


def test_refresh_and_outbound_helper_syntax_check() -> None:
    for script in (_REFRESH, _OUTBOUND_HELPER):
        cp = subprocess.run(
            ["bash", "-n", str(script)],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert cp.returncode == 0, cp.stderr
