"""Sanity checks for Alembic PostgreSQL scaffolding (no DB required)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260419_0001_initial_schemas_and_ops.py"


def test_initial_migration_file_exists() -> None:
    assert MIGRATION.is_file()


def test_initial_migration_defines_schemas_and_ops_ddl() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CASCADE" not in text
    assert 'op.execute(f"CREATE SCHEMA IF NOT EXISTS {name}")' in text
    for s in ("archive", "ops", "mart", "leads", "commercial", "outbound", "supplier", "reporting"):
        assert f'"{s}"' in text or f"'{s}'" in text
    assert "CREATE TABLE ops.pipeline_run" in text
    assert "CREATE TABLE ops.pipeline_kv" in text
    assert "kv_key TEXT PRIMARY KEY" in text
    assert "idx_ops_pipeline_run_started" in text
    assert "metadata_json JSONB" in text
    assert 'op.execute(f"DROP SCHEMA IF EXISTS {name}")' in text


def test_alembic_upgrade_fails_without_database_url() -> None:
    """Migration commands must not fall back to SQLite or a default localhost URL."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k not in ("ALEMBIC_DATABASE_URL", "ORIGENLAB_POSTGRES_URL")}
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "import alembic.config; alembic.config.main(argv=['upgrade', 'head'])",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert r.returncode != 0
    combined = (r.stderr or "") + (r.stdout or "")
    assert "ALEMBIC_DATABASE_URL" in combined
    assert "ORIGENLAB_POSTGRES_URL" in combined
    assert "SQLite runtime is not used by Alembic" in combined


@pytest.mark.skipif(
    not __import__("os").environ.get("ALEMBIC_DATABASE_URL"),
    reason="Set ALEMBIC_DATABASE_URL to run upgrade smoke test against PostgreSQL.",
)
def test_alembic_upgrade_head_smoke() -> None:
    """Optional: uv run pytest --run-alembic-smoke with URL set, or export ALEMBIC_DATABASE_URL."""
    import subprocess
    import sys

    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "import alembic.config; alembic.config.main(argv=['upgrade', 'head'])",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr + r.stdout
