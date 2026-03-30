"""Shared UTC timestamps for pipeline rows and metadata (single format)."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """UTC wall time as ``YYYY-MM-DDTHH:MM:SSZ`` (no fractional seconds)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
