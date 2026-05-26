"""Static and stubbed tests for refresh_render_dashboard_once.sh (Phase 6)."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_REFRESH = _REPO / "scripts/ops/refresh_render_dashboard_once.sh"
_COMMERCIAL_HELPER = _REPO / "scripts/ops/_refresh_commercial_deal_mirror.sh"
_FORBIDDEN_INVOCATIONS = (
    "send_inline_html",
    "mark_sent_batch",
    "mark_outreach_state",
    "refresh_outbound_safety_memory",
    "promote_deal_from_preview",
    "build_business_mart.py --rebuild",
    "build_commercial_intel_v1.py --rebuild",
)


def _script_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_refresh_script_default_commercial_mirror_off() -> None:
    text = _script_text(_REFRESH)
    assert 'RUN_COMMERCIAL_DEAL_MIRROR="${RUN_COMMERCIAL_DEAL_MIRROR:-0}"' in text
    assert 'RUN_COMMERCIAL_DEAL_MIRROR" == "1"' in text
    assert "COMMERCIAL_MIRROR_STATUS=\"skipped\"" in text or 'COMMERCIAL_MIRROR_STATUS="skipped"' in text


def test_refresh_script_when_commercial_enabled_runs_dry_run_sync_verify() -> None:
    text = _script_text(_REFRESH) + _script_text(_COMMERCIAL_HELPER)
    assert "sync_commercial_deals_postgres_mirror.py --dry-run" in text
    assert "sync_commercial_deals_postgres_mirror.py" in text
    assert "verify_commercial_deals_postgres_mirror.py" in text
    assert "--scan-jsonb" in text
    assert "/tmp/commercial_deals_mirror_verify.json" in text


def test_commercial_helper_verify_failure_message_and_exit() -> None:
    text = _script_text(_COMMERCIAL_HELPER)
    assert "Commercial deal mirror verify failed" in text
    assert "commercial deal data should not be trusted" in text
    assert "return 1" in text


def test_refresh_script_does_not_invoke_send_or_outreach() -> None:
    runtime_lines = [
        ln
        for ln in _script_text(_REFRESH).splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    runtime = "\n".join(runtime_lines)
    for forbidden in _FORBIDDEN_INVOCATIONS:
        assert forbidden not in runtime, f"refresh script must not call {forbidden}"


def test_refresh_script_syntax_check() -> None:
    cp = subprocess.run(
        ["bash", "-n", str(_REFRESH)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert cp.returncode == 0, cp.stderr


def test_commercial_helper_failure_stops_with_nonzero_exit(tmp_path: Path) -> None:
    """Stub uv so verify fails; sourced helper must return 1."""
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
              if [[ "$script" == *verify_commercial_deals_postgres_mirror.py* ]]; then
                exit 1
              fi
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    uv_stub.chmod(0o755)

    runner = tmp_path / "run_commercial.sh"
    runner.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -eo pipefail
            export PATH="{stub_bin}:$PATH"
            export ORIGENLAB_SQLITE_PATH="{tmp_path / 'emails.sqlite'}"
            # shellcheck source=scripts/ops/_refresh_commercial_deal_mirror.sh
            source "{_COMMERCIAL_HELPER}"
            run_commercial_deal_mirror_refresh "{_REPO}" "{tmp_path / 'verify.json'}"
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
    assert "Commercial deal mirror verify failed" in cp.stderr
