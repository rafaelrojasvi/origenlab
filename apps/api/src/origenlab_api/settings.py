"""API settings (read-only paths)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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
