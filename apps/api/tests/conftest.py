"""Shared pytest fixtures for apps/api."""

from __future__ import annotations

import pytest

from origenlab_api.settings import get_settings


@pytest.fixture(autouse=True)
def _isolate_origenlab_api_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tests to SQLite backend unless they set env explicitly."""
    monkeypatch.delenv("ORIGENLAB_API_BACKEND", raising=False)
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
