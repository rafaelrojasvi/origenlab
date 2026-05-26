"""Tests for verify_commercial_deals_postgres_mirror path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.qa.verify_commercial_deals_postgres_mirror import (  # noqa: E402
    resolve_verify_sqlite_path,
)


def test_resolve_verify_sqlite_path_uses_explicit_path(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite"
    db.write_bytes(b"")
    resolved = resolve_verify_sqlite_path(db)
    assert resolved == db.resolve()


def test_resolve_verify_sqlite_path_wraps_env_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "from-env.sqlite"
    db.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))
    resolved = resolve_verify_sqlite_path(None)
    assert resolved == db.resolve()


def test_resolve_verify_sqlite_path_env_string_is_not_passed_raw_to_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: env string must become Path before resolve_sqlite_path expanduser()."""
    monkeypatch.delenv("ORIGENLAB_SQLITE_PATH", raising=False)
    with pytest.raises((TypeError, AttributeError)):
        # Caller mistake we fixed: resolve_sqlite_path("literal-string-path")
        from origenlab_email_pipeline.mart_core_postgres_migrate import resolve_sqlite_path

        resolve_sqlite_path("/tmp/example.sqlite")  # type: ignore[arg-type]
