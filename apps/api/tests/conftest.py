"""Shared pytest fixtures for apps/api."""

from __future__ import annotations

import pytest

from origenlab_api.settings import get_settings


@pytest.fixture(autouse=True)
def _isolate_origenlab_api_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tests to SQLite backend unless they set env explicitly."""
    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "sqlite")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
