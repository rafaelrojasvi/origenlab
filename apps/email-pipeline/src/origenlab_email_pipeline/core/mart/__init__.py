"""Stable **mart** import surface (business mart build + schema). Re-exports only."""

from __future__ import annotations

from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.build_runner import ensure_fast_indexes, run_business_mart_build

__all__ = [
    "MartBuildOptions",
    "ensure_fast_indexes",
    "run_business_mart_build",
]
