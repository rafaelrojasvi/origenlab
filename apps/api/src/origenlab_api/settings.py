"""API settings (read-only paths)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ApiBackend = Literal["sqlite", "postgres"]

_API_ROOT = Path(__file__).resolve().parents[2]
_EMAIL_PIPELINE_ROOT = _API_ROOT.parent / "email-pipeline"
_DEFAULT_ACTIVE_CURRENT = _EMAIL_PIPELINE_ROOT / "reports" / "out" / "active" / "current"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORIGENLAB_",
        env_file=".env",
        extra="ignore",
    )

    sqlite_path: Path | None = None
    active_current: Path | None = None
    api_backend: str | None = None
    postgres_url: str | None = None
    postgres_statement_timeout_ms: int = 30_000
    postgres_pool_size: int = 5
    """Comma-separated browser origins for dashboard static site (no wildcards)."""
    api_cors_origins: str | None = None
    """When true, hide /docs, /redoc, /openapi.json (also off when ORIGENLAB_ENV=production)."""
    api_disable_docs: bool = False
    """Set to production|prod to enable production defaults (docs off, stricter validation)."""
    env: str | None = None

    def production_mode(self) -> bool:
        return (self.env or "").strip().lower() in ("production", "prod")

    def parsed_cors_origins(self) -> list[str]:
        raw = (self.api_cors_origins or "").strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    def resolved_api_backend(self) -> ApiBackend:
        raw = (self.api_backend or "sqlite").strip().lower()
        if raw not in ("sqlite", "postgres"):
            raise ValueError(
                f"Invalid ORIGENLAB_API_BACKEND={raw!r} (expected 'sqlite' or 'postgres')"
            )
        return raw  # type: ignore[return-value]

    def postgres_configured(self) -> bool:
        return bool((self.postgres_url or "").strip())

    def require_postgres_url(self) -> str:
        url = (self.postgres_url or "").strip()
        if not url:
            raise ValueError(
                "ORIGENLAB_POSTGRES_URL is required when ORIGENLAB_API_BACKEND=postgres"
            )
        return url

    def resolved_sqlite_path(self) -> Path:
        if self.sqlite_path is not None:
            return self.sqlite_path.expanduser().resolve()
        from origenlab_email_pipeline.config import load_settings

        return load_settings().resolved_sqlite_path()

    def resolved_active_current(self) -> Path:
        if self.active_current is not None:
            return self.active_current.expanduser().resolve()
        return _DEFAULT_ACTIVE_CURRENT.resolve()

    def resolved_manifest_path(self) -> Path:
        return self.resolved_active_current() / "manifest.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
