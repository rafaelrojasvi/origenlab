"""Postgres read queries for dashboard API (Slice 1 mart lists)."""

from __future__ import annotations

from origenlab_email_pipeline.postgres_dashboard_api.mart_lists import (
    list_contacts,
    list_organizations,
)

__all__ = ["list_contacts", "list_organizations"]
