"""Load settings from environment. No repo-specific or private paths in code."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_root() -> Path:
    return Path.home() / "data" / "origenlab-email"

def _repo_root() -> Path:
    # src/origenlab_email_pipeline/config.py -> repo root
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORIGENLAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_root: Path = Field(default_factory=_default_data_root)

    raw_pst_dir: Path | None = Field(default=None, description="Directory containing .pst files")
    mbox_dir: Path | None = Field(default=None, description="Directory with mbox trees from readpst")
    sqlite_path: Path | None = Field(default=None, description="SQLite DB path")
    jsonl_path: Path | None = Field(default=None, description="JSONL output path")
    reports_dir: Path | None = Field(
        default=None,
        description="Client reports root (timestamped runs under here)",
    )

    gmail_oauth_client_json: str | None = Field(
        default=None,
        description="Path to Google Cloud Desktop OAuth client JSON (Gmail IMAP ingest)",
    )
    gmail_workspace_user: str | None = Field(
        default=None,
        description="Workspace mailbox address for Gmail IMAP (e.g. contacto@domain)",
    )
    gmail_token_json: str | None = Field(
        default=None,
        description="Optional path for Gmail OAuth refresh token JSON",
    )
    gmail_oauth_open_browser: bool = Field(
        default=True,
        description="If false, print OAuth URL only (use on WSL when xdg-open/gio fails)",
    )

    def resolved_raw_pst_dir(self) -> Path:
        return self.raw_pst_dir or (self.data_root / "raw_pst")

    def resolved_mbox_dir(self) -> Path:
        return self.mbox_dir or (self.data_root / "mbox")

    def resolved_sqlite_path(self) -> Path:
        return self.sqlite_path or (self.data_root / "sqlite" / "emails.sqlite")

    def resolved_jsonl_path(self) -> Path:
        return self.jsonl_path or (self.data_root / "jsonl" / "emails.jsonl")

    def resolved_reports_dir(self) -> Path:
        # Default to repo-local reports to keep outputs discoverable.
        # Can be overridden via ORIGENLAB_REPORTS_DIR for large runs outside repo.
        return self.reports_dir or (_repo_root() / "reports" / "out")


def load_settings() -> Settings:
    return Settings()
