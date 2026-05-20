"""Shared types for contact detail repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ContactQueryResult:
    contact: dict[str, Any]
    outreach: dict[str, Any]
    sent_history: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    reduced_mode: bool = False
    data_source: Literal["sqlite", "postgres_mirror"] = "sqlite"
