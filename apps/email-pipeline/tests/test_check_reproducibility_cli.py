from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "check_reproducibility.py"


def _env_base() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(REPO / "src")}


def _run(*extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    e = _env_base() if env is None else env
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        cwd=str(REPO),
        env=e,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_check_reproducibility_help() -> None:
    r = _run("--help")
    assert r.returncode == 0
    out = (r.stdout or "") + (r.stderr or "")
    assert "reproducibility" in out.lower() or "usage" in out.lower()


def test_runs_exit_zero_without_db() -> None:
    missing = REPO / "this_path_should_not_exist_repro_test.sqlite"
    r = _run(
        env={
            **_env_base(),
            "ORIGENLAB_SQLITE_PATH": str(missing),
        },
    )
    assert r.returncode == 0
    assert "verdict: code_only_ready" in r.stdout
    assert "supersecret" not in r.stdout


def test_does_not_print_gmail_env_values() -> None:
    secret = "xxyyzz_secret_token_do_not_leak_123"
    r = _run(
        env={
            **_env_base(),
            "ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON": secret,
            "ORIGENLAB_GMAIL_TOKEN_JSON": secret,
            "ORIGENLAB_GMAIL_WORKSPACE_USER": f"u{secret}@example.com",
        },
    )
    assert r.returncode == 0
    assert secret not in r.stdout
    assert secret not in (r.stderr or "")
    assert "set (value not shown)" in r.stdout


def test_empty_sqlite_reports_missing_private_runtime_gracefully(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(str(db)).close()
    r = _run(
        env={
            **_env_base(),
            "ORIGENLAB_SQLITE_PATH": str(db),
        },
    )
    assert r.returncode == 0
    assert "verdict: missing_private_runtime_inputs" in r.stdout
    assert "table emails: no" in r.stdout
