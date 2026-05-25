"""Tests for cloud Postgres URL shell helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.cloud_postgres_url import (
    ensure_psycopg_driver_url,
    postgres_url_host_db,
    shell_prepare_lines,
    validate_cloud_postgres_url,
)

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "scripts" / "ops" / "cloud_postgres_url.py"


def test_normalize_render_style_url() -> None:
    raw = "postgresql://admin:pass)word@dpg-abc.oregon-postgres.render.com:5432/origenlab_dashboard_prod"
    assert ensure_psycopg_driver_url(raw) == (
        "postgresql+psycopg://admin:pass)word@dpg-abc.oregon-postgres.render.com:5432/"
        "origenlab_dashboard_prod"
    )


def test_normalize_preserves_psycopg_prefix() -> None:
    raw = "postgresql+psycopg://u:p@host.example.com/db"
    assert ensure_psycopg_driver_url(raw) == raw


def test_host_db_never_includes_password() -> None:
    raw = "postgresql://admin:secret@dpg-abc.render.com/origenlab_dashboard_prod"
    display = postgres_url_host_db(raw)
    assert display == "dpg-abc.render.com/origenlab_dashboard_prod"
    assert "secret" not in display
    assert "admin" not in display


def test_validate_rejects_empty_and_placeholders() -> None:
    assert validate_cloud_postgres_url("")
    assert validate_cloud_postgres_url("postgresql+psycopg://USER:PASSWORD@HOST/DB")
    assert validate_cloud_postgres_url("postgresql://user:pass@host/dbname")


def test_shell_prepare_password_with_special_chars() -> None:
    raw = "postgresql://admin:pass)word@dpg-x.render.com/mydb"
    code, lines = shell_prepare_lines(raw)
    assert code == 0
    assert "pass)word" in lines
    assert "HOST_DB=dpg-x.render.com/mydb" in lines
    assert "postgresql+psycopg://" in lines


def test_resolve_postgres_url_falls_back_to_cloud_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from origenlab_email_pipeline.mart_core_postgres_migrate import resolve_postgres_url

    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "ORIGENLAB_CLOUD_POSTGRES_URL",
        "postgresql://admin:pass)word@dpg-x.render.com/origenlab_dashboard_prod",
    )
    assert (
        resolve_postgres_url(None)
        == "postgresql://admin:pass)word@dpg-x.render.com/origenlab_dashboard_prod"
    )


def test_dotenv_export_preserves_password_with_paren(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ORIGENLAB_CLOUD_POSTGRES_URL=postgresql://admin:pass)word@dpg-x.render.com/mydb\n",
        encoding="utf-8",
    )
    cp = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from dotenv import dotenv_values
import shlex
for key, value in dotenv_values(".env").items():
    if value:
        print(f"export {key}={shlex.quote(str(value))}")
""",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "pass)word" in cp.stdout
    assert "postgresql://" in cp.stdout


def test_cli_prepare_subprocess() -> None:
    env = {
        **dict(__import__("os").environ),
        "ORIGENLAB_CLOUD_POSTGRES_URL": (
            "postgresql://u:p@dpg-test.oregon-postgres.render.com/origenlab_dashboard_prod"
        ),
    }
    cp = subprocess.run(
        [sys.executable, str(CLI), "prepare"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stderr
    assert "NORMALIZED_URL=" in cp.stdout
    assert "postgresql+psycopg://" in cp.stdout
    host_line = next(line for line in cp.stdout.splitlines() if line.startswith("HOST_DB="))
    assert host_line == "HOST_DB=dpg-test.oregon-postgres.render.com/origenlab_dashboard_prod"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "postgresql+psycopg://USER:PASSWORD@HOST/DB",
    ],
)
def test_cli_validate_fails(url: str) -> None:
    cp = subprocess.run(
        [sys.executable, str(CLI), "validate", *(["--url", url] if url else [])],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 2
