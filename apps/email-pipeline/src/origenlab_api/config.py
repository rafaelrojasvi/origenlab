"""API configuration (Postgres URL, optional SQLite ping for health only)."""

from __future__ import annotations

import os
from functools import lru_cache

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.postgres_outbound_audit import (
    OutboundAuditError,
    redact_postgres_url,
    resolve_postgres_url,
)


class ApiConfigError(RuntimeError):
    """Misconfiguration (e.g. missing Postgres URL)."""


@lru_cache(maxsize=1)
def get_api_settings() -> dict[str, str | bool]:
    """Resolved settings for the API process (cached)."""
    settings = load_settings()
    try:
        url = resolve_postgres_url(
            None,
            require_when_requested=True,
            audit_requested=True,
        )
    except OutboundAuditError as exc:
        raise ApiConfigError(str(exc)) from exc
    if not url:
        raise ApiConfigError(
            "Postgres URL required. Set ORIGENLAB_POSTGRES_URL or ALEMBIC_DATABASE_URL."
        )
    return {
        "postgres_url": url,
        "postgres_url_redacted": redact_postgres_url(url),
        "sqlite_path": str(settings.resolved_sqlite_path()),
        "gmail_user": (settings.gmail_workspace_user or "contacto@origenlab.cl").strip(),
    }


def reset_api_settings_cache() -> None:
    get_api_settings.cache_clear()
