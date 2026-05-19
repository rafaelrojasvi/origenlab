"""Shared API response metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ResponseMeta(BaseModel):
    generated_at: str = Field(default_factory=utc_now_iso)
    data_source: Literal["sqlite"] = "sqlite"
    read_only: bool = True
    sqlite_path_redacted: str = "<unset>"

    @classmethod
    def for_sqlite(cls, sqlite_path: Path | None) -> ResponseMeta:
        redacted = "<set>" if sqlite_path is not None and sqlite_path.is_file() else "<unset>"
        return cls(sqlite_path_redacted=redacted)
